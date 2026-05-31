"""Application aggregator: owns brokers, runs them concurrently, manages lifecycle hooks.

A top-level container that user code constructs at module load time and runs via
`asyncio.run(app.run())`. Brokers are lazy: `MemoryBroker()` and `NatsBroker(url)` do not
open any resources; the app calls `broker.start()` during `run()` and `broker.stop()` on
shutdown.

Lifecycle hooks fire in this order:

* ``on_startup``: before any broker connects. Init resources, load config.
* ``after_startup``: after every broker connected. Brokers are live; publish initial
  messages, warm caches.
* ``on_shutdown``: before brokers disconnect. Brokers are still live; flush state.
* ``after_shutdown``: after every broker stopped. Release resources.

Lifecycle hooks and the lifespan factory share the same DI-driven binding as handler
parameters: every positional parameter is resolved through the app's :class:`DI`
provider (default :class:`NoOpDI`). Under the default, an annotation of
``context: ContextRepo`` receives the shared context; ecosystem DI adapters extend the
supported domain (``ctx: FromDishka[ContextRepo]`` under ``DishkaDI``,
``ctx: ContextRepo = Depends(Context)`` under ``FastDependsDI``).

The optional ``lifespan`` async context manager wraps the dispatch phase: setup runs
between ``on_startup`` and broker start, teardown runs between broker stop and
``after_shutdown``.

Example:

    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator

    from ruststream import ContextRepo, RustStream
    from ruststream_nats import NatsBroker, NatsRouter

    broker = NatsBroker("nats://127.0.0.1:4222")
    router = NatsRouter()

    @router.subscriber("orders")
    async def handle(msg):
        ...

    broker.include_router(router)

    @asynccontextmanager
    async def lifespan(context: ContextRepo) -> AsyncIterator[None]:
        context.set_global("rlm", await acquire_lock())
        yield
        context.reset_global("rlm")

    app = RustStream(broker, lifespan=lifespan, title="orders-service")

    @app.on_startup
    async def load_config(context: ContextRepo) -> None:
        context.set_global("settings", Settings())

    @app.after_startup
    async def announce() -> None:
        await broker.publish("system.ready", b"online")
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

from ruststream._broker import Broker
from ruststream._signature import collect_dependencies
from ruststream.context import ContextRepo
from ruststream.di import DI, NoOpDI

logger = logging.getLogger(__name__)

Lifecycle = Callable[..., Awaitable[None]]
LifespanFactory = Callable[..., contextlib.AbstractAsyncContextManager[Any]]


@dataclass(slots=True)
class _Hooks:
    on_startup: list[Lifecycle] = field(default_factory=list)
    after_startup: list[Lifecycle] = field(default_factory=list)
    on_shutdown: list[Lifecycle] = field(default_factory=list)
    after_shutdown: list[Lifecycle] = field(default_factory=list)


class RustStream:
    """Application container that owns brokers and orchestrates their lifecycle.

    Args:
        broker: Optional initial broker. Pass ``None`` and use :meth:`add_broker` for
            multi-broker applications, or pass a single broker for the common case.
        lifespan: Optional async context manager factory that receives a :class:`ContextRepo`
            and wraps the dispatch phase: setup runs after ``on_startup`` and before any
            broker starts; teardown runs after every broker stops and before
            ``after_shutdown``.
        title: Free-form human label, surfaced in logs and (later) AsyncAPI metadata.

    Attributes:
        context: :class:`ContextRepo` shared with lifespan, hooks (when declared in their
            signature), and handler DI providers.
        title: The label passed to the constructor.
    """

    def __init__(
        self,
        broker: Broker | None = None,
        *,
        lifespan: LifespanFactory | None = None,
        di: DI | None = None,
        title: str = "RustStream",
    ) -> None:
        self.title = title
        self.context: ContextRepo = ContextRepo()
        self._lifespan = lifespan
        self._di: DI = di if di is not None else NoOpDI()
        self._brokers: list[Broker] = []
        if broker is not None:
            self._brokers.append(broker)
        self._hooks = _Hooks()
        self._stop_event: asyncio.Event = asyncio.Event()
        self._ready_event: asyncio.Event = asyncio.Event()
        self._run_task: asyncio.Task[None] | None = None

    def add_broker(self, broker: Broker) -> None:
        """Register an additional broker. The app starts and stops every registered broker."""
        self._brokers.append(broker)

    @property
    def brokers(self) -> tuple[Broker, ...]:
        return tuple(self._brokers)

    def on_startup(self, callback: Lifecycle) -> Lifecycle:
        """Register a hook to run before any broker connects. Usable as a decorator.

        Brokers are not yet started; do not publish here. Use ``after_startup`` instead.
        """
        self._hooks.on_startup.append(callback)
        return callback

    def after_startup(self, callback: Lifecycle) -> Lifecycle:
        """Register a hook to run after every broker has connected. Usable as a decorator.

        Brokers are live: safe to publish initial messages or warm caches.
        """
        self._hooks.after_startup.append(callback)
        return callback

    def on_shutdown(self, callback: Lifecycle) -> Lifecycle:
        """Register a hook to run before brokers disconnect. Usable as a decorator.

        Brokers are still live: safe to flush state or publish farewell messages.
        """
        self._hooks.on_shutdown.append(callback)
        return callback

    def after_shutdown(self, callback: Lifecycle) -> Lifecycle:
        """Register a hook to run after every broker has stopped. Usable as a decorator.

        Brokers are gone; use this for releasing non-broker resources.
        """
        self._hooks.after_shutdown.append(callback)
        return callback

    def shutdown(self) -> None:
        """Trigger a graceful shutdown. Safe to call from a signal handler."""
        self._stop_event.set()

    async def run(self) -> None:
        """Drive the full lifecycle: ``on_startup`` → lifespan enter → brokers start →
        ``after_startup`` → wait → ``on_shutdown`` → brokers stop → lifespan exit →
        ``after_shutdown``.

        Startup-side hooks (``on_startup``, ``after_startup``) and broker start are
        fatal: a failure aborts ``run``. Shutdown-side steps run best-effort with
        logging.
        """
        await self._call_hooks("on_startup", self._hooks.on_startup, fatal=True)
        try:
            async with self._enter_lifespan():
                started: list[Broker] = []
                try:
                    for broker in self._brokers:
                        broker._context = self.context
                        await broker.start()
                        started.append(broker)
                    await self._call_hooks("after_startup", self._hooks.after_startup, fatal=True)
                    self._ready_event.set()
                    await self._stop_event.wait()
                finally:
                    await self._call_hooks("on_shutdown", self._hooks.on_shutdown, fatal=False)
                    for broker in reversed(started):
                        try:
                            await broker.stop()
                        except Exception:
                            logger.exception("broker stop raised in %s", self.title)
        finally:
            await self._call_hooks("after_shutdown", self._hooks.after_shutdown, fatal=False)
            try:
                await self._di.aclose()
            except Exception:
                logger.exception("app DI aclose raised in %s", self.title)

    async def __aenter__(self) -> Self:
        """Start ``run()`` in a background task and wait until every broker is up.

        Returns once ``after_startup`` hooks have completed, so user code following
        ``async with app:`` can safely publish without racing broker subscription. If
        ``run()`` raises before reaching the ready signal (failed broker connect,
        ``on_startup``/``after_startup`` hook error), the exception propagates here.
        """
        if self._run_task is not None and not self._run_task.done():
            raise RuntimeError("RustStream is already running")
        self._ready_event.clear()
        self._stop_event.clear()
        self._run_task = asyncio.create_task(self.run())
        ready_wait = asyncio.create_task(self._ready_event.wait())
        try:
            done, _ = await asyncio.wait(
                {self._run_task, ready_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            ready_wait.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ready_wait
        if self._run_task in done and not self._ready_event.is_set():
            # run() raised before broker startup signalled ready; propagate the exception.
            exc = self._run_task.exception()
            if exc is not None:
                raise exc
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.shutdown()
        if self._run_task is None:
            return
        try:
            await self._run_task
        except asyncio.CancelledError:
            pass
        except BaseExceptionGroup as group:
            for inner in group.exceptions:
                if not isinstance(inner, asyncio.CancelledError):
                    raise
        finally:
            self._run_task = None

    @contextlib.asynccontextmanager
    async def _enter_lifespan(self) -> AsyncGenerator[None, None]:
        if self._lifespan is None:
            yield
            return
        args = await self._resolve_call_args(self._lifespan, label="lifespan")
        async with self._lifespan(*args):
            yield

    async def _call_hooks(self, kind: str, hooks: list[Lifecycle], *, fatal: bool) -> None:
        for callback in hooks:
            try:
                args = await self._resolve_call_args(callback, label=kind)
                await callback(*args)
            except Exception:
                logger.exception("%s hook raised in %s", kind, self.title)
                if fatal:
                    raise

    async def _resolve_call_args(
        self,
        callback: Callable[..., Any],
        *,
        label: str,
    ) -> list[Any]:
        """Build the positional argument list for `callback` by routing each parameter
        through the app's :class:`DI` provider.

        Lifespan factory and lifecycle hooks share the same DI-driven binding: every
        positional parameter (annotated) must be supported by the active DI, and is
        resolved against the app's :class:`ContextRepo`. Callables with no positional
        parameters are invoked with no arguments.
        """
        deps = collect_dependencies(callback, skip_first=False)
        if not deps:
            return []
        resolved: list[Any] = []
        for dep in deps:
            if not self._di.supports(dep.annotation, dep.default):
                ann_name = getattr(dep.annotation, "__name__", repr(dep.annotation))
                raise TypeError(
                    f"DI provider {self._di.name!r} cannot resolve {label} "
                    f"parameter {dep.name!r}: {ann_name}",
                )
            resolved.append(
                await self._di.resolve(
                    dep.annotation,
                    context=self.context,
                    default=dep.default,
                ),
            )
        return resolved


__all__: tuple[str, ...] = ("RustStream",)
