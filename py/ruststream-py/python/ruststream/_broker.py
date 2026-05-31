"""Shared broker base used by each broker package.

`Broker` provides the common machinery (subscriber/publisher decorators, include_router,
dispatch loop, lifecycle) for any concrete broker implementation. Subclasses plug in
broker-specific connect/publish/subscribe primitives by implementing the abstract methods
below.
"""

import asyncio
import contextlib
import inspect
import logging
import typing
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, NamedTuple

from ruststream._message import Message
from ruststream._native import Message as _NativeMessage
from ruststream._native import Subscriber
from ruststream._signature import _Dependency, _positional_params, collect_dependencies
from ruststream.codecs import Codec, resolve_codec
from ruststream.context import ContextRepo
from ruststream.di import DI, NoOpDI
from ruststream.failure import FailureAction, FailurePolicy, resolve_failure_action
from ruststream.metrics import MetricsRecorder, NullMetrics
from ruststream.validators import resolve_validator

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[Any]]


class _PublishTarget(NamedTuple):
    """Pair of (destination topic, optional codec override) attached by `@publisher`."""

    topic: str
    codec: Codec | str | None


_PUBLISH_TO_ATTR = "__ruststream_publish_to__"


def _mark_publish_to(handler: Handler, topic: str, codec: Codec | str | None) -> None:
    existing: list[_PublishTarget] = getattr(handler, _PUBLISH_TO_ATTR, [])
    existing.insert(0, _PublishTarget(topic, codec))
    setattr(handler, _PUBLISH_TO_ATTR, existing)


def _drain_publish_to(handler: Handler) -> list[_PublishTarget]:
    return list(getattr(handler, _PUBLISH_TO_ATTR, []))


@dataclass(slots=True)
class _Registration:
    topic: str
    handler: Handler
    options: dict[str, Any] = field(default_factory=dict)
    publish_to: list[_PublishTarget] = field(default_factory=list)
    codec: Codec | str | None = None
    di: DI | None = None


_RAW_PAYLOAD_TYPES: tuple[type, ...] = (bytes, bytearray, memoryview)


def _payload_type_of(handler: Handler) -> type | None:
    """Return the annotation of the handler's first positional parameter, if any.

    `None` is returned for handlers whose first parameter has no annotation, is annotated
    as `Message`, or whose signature cannot be introspected. `Annotated[X, ...]` wrappers
    are unwrapped so validators see the underlying `X`.
    """
    positional = _positional_params(handler)
    if not positional:
        return None
    first = positional[0]
    if first.annotation is inspect.Parameter.empty:
        return None
    try:
        annotation = typing.get_type_hints(handler, include_extras=True).get(first.name)
    except Exception:
        annotation = None
    if annotation is None or annotation is Message:
        return None
    if typing.get_origin(annotation) is Annotated:
        annotation = typing.get_args(annotation)[0]
    return annotation if isinstance(annotation, type) else None


@dataclass(slots=True)
class Router:
    """Reusable bundle of subscriber registrations to attach to a broker later.

    Supports the same `subscriber(topic, **options)` and `publisher(topic)` decorators as
    `Broker` itself; the actual broker connection is provided at `include_router` time, so
    routers stay broker-agnostic and freely composable.
    """

    registrations: list[_Registration] = field(default_factory=list)

    def subscriber(
        self,
        topic: str,
        *,
        codec: Codec | str | None = None,
        di: DI | None = None,
        **options: Any,
    ) -> Callable[[Handler], Handler]:
        """Register `handler` under `topic` with optional broker-specific kwargs.

        Args:
            topic: Subject / queue / topic pattern the handler subscribes to.
            codec: Optional codec override for decoding incoming payloads. `None` falls
                back to the host broker's default codec when the handler signature
                triggers validation.
            di: Optional DI override for this subscriber. `None` defers to the host
                broker's DI provider at `include_router` time.
            **options: Broker-specific subscription options (e.g. `queue_group="workers"`,
                `jetstream="ORDERS"`, `durable="worker-1"`, `ack_wait=30.0`,
                `max_ack_pending=64`, `deliver_policy="new"`). The active broker's
                `_subscribe` method receives them as keyword arguments.
        """

        def decorator(handler: Handler) -> Handler:
            self.registrations.append(
                _Registration(
                    topic=topic,
                    handler=handler,
                    options=dict(options),
                    publish_to=_drain_publish_to(handler),
                    codec=codec,
                    di=di,
                ),
            )
            return handler

        return decorator

    def publisher(
        self,
        topic: str,
        *,
        codec: Codec | str | None = None,
    ) -> Callable[[Handler], Handler]:
        """Mark `handler` so its return value (if not None) is republished to `topic` once
        the host broker has been attached via `include_router`.

        Args:
            topic: Destination topic for the handler's return value.
            codec: Optional codec override. `None` falls back to the broker's default codec
                at publish time, so the same router stays portable across brokers with
                different defaults.

        Multiple `@publisher(...)` decorators may be stacked; the return value is forwarded
        to every listed topic. The actual publish happens through whichever broker adopts
        the registration.
        """

        def decorator(handler: Handler) -> Handler:
            _mark_publish_to(handler, topic, codec)
            return handler

        return decorator


class Broker(ABC):
    """Base class for broker wrappers.

    Subclasses provide concrete `_open` (connect / setup), `_close` (disconnect / teardown),
    `_subscribe` (open a single subscription) and `_publish` (send one message).
    Handler dispatch, lifecycle, and decorator API live here.
    """

    def __init__(
        self,
        *,
        on_error: FailurePolicy = None,
        codec: Codec | str | None = None,
        di: DI | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._registrations: list[_Registration] = []
        self._tasks: list[asyncio.Task[None]] = []
        self._started: bool = False
        self._on_error: FailurePolicy = on_error
        self._default_codec: Codec = resolve_codec(codec)
        self._di: DI = di if di is not None else NoOpDI()
        self._metrics: MetricsRecorder = metrics if metrics is not None else NullMetrics()
        self._context: ContextRepo = ContextRepo()

    def subscriber(
        self,
        topic: str,
        *,
        codec: Codec | str | None = None,
        di: DI | None = None,
        **options: Any,
    ) -> Callable[[Handler], Handler]:
        """Register `handler` as the subscriber for `topic`. Usable as a decorator.

        Accepts broker-specific kwargs (e.g. `queue_group`, `jetstream`, `durable`,
        `ack_wait`, `max_ack_pending`, `deliver_policy`, `start_sequence`,
        `filter_subject`). Unknown kwargs are forwarded to the broker's `_subscribe`
        method; brokers that do not understand a given kwarg raise `TypeError` from the
        native layer.

        Args:
            topic: Subject / queue / topic pattern.
            codec: Optional codec override for decoding incoming payloads when the
                handler's first parameter is a validated model. `None` uses the broker's
                default codec.
            di: Optional DI override for this subscriber. `None` uses the broker's DI.
        """

        def decorator(handler: Handler) -> Handler:
            self._registrations.append(
                _Registration(
                    topic=topic,
                    handler=handler,
                    options=dict(options),
                    publish_to=_drain_publish_to(handler),
                    codec=codec,
                    di=di,
                ),
            )
            return handler

        return decorator

    def publisher(
        self,
        topic: str,
        *,
        codec: Codec | str | None = None,
    ) -> Callable[[Handler], Handler]:
        """Mark `handler` so its return value (if not None) is republished to `topic`.

        Args:
            topic: Destination topic for the handler's return value.
            codec: Optional codec override for this topic. `None` falls back to the
                broker's default codec (set on `__init__`); pass a name (`"json"`,
                `"orjson"`, ...) or a `Codec` instance to override.

        Stackable with other `@publisher(...)` decorators; every listed topic receives
        the return value encoded through its own codec. Combine with `@subscriber(...)` to
        register the handler; the publisher wrapping is applied on `start()`.
        """

        def decorator(handler: Handler) -> Handler:
            _mark_publish_to(handler, topic, codec)
            return handler

        return decorator

    def include_router(self, router: Router) -> None:
        """Adopt every subscriber registration from `router`."""
        self._registrations.extend(router.registrations)

    @property
    def registrations(self) -> tuple[_Registration, ...]:
        return tuple(self._registrations)

    async def publish(
        self,
        topic: str,
        value: Any,
        *,
        codec: Codec | str | None = None,
    ) -> None:
        """Publish `value` to `topic`, encoding via the resolved codec.

        Args:
            topic: Destination topic.
            value: Payload to publish. With `RawBytesCodec` (the default unless overridden
                on `__init__`) `value` must be bytes-like; any other codec accepts whatever
                the underlying serializer takes (a `dict` for JSON, `dict` / list / scalars
                for msgpack, etc.).
            codec: Override the broker's default codec for this single call.
        """
        active = resolve_codec(codec, fallback=self._default_codec)
        await self._publish(topic, active.encode(value))

    async def start(self) -> None:
        """Connect, open every registered subscription, and start dispatching."""
        if self._started:
            return
        await self._open()
        self._started = True
        for reg in self._registrations:
            handler = self._build_handler_chain(reg)
            subscriber = await self._subscribe(reg.topic, **reg.options)
            task = asyncio.create_task(self._dispatch(subscriber, handler, reg.topic))
            self._tasks.append(task)

    async def stop(self) -> None:
        """Stop dispatching, cancel pending tasks, and disconnect."""
        if not self._started:
            return
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._close()
        await self._di.aclose()
        self._context.clear_session()
        self._started = False

    def _build_handler_chain(self, reg: _Registration) -> Handler:
        """Wrap `reg.handler` with payload validation, DI injection, and publisher fanout.

        Order (innermost to outermost):
            1. Original handler (`reg.handler`).
            2. `_wrap_dependencies`: resolves trailing parameters through DI.
            3. `_wrap_publishers`: forwards the return value to publisher topics.
            4. `_wrap_validated`: decodes the wire bytes into the payload value.
        """
        active_di = reg.di if reg.di is not None else self._di
        payload_type = _payload_type_of(reg.handler)
        dependencies = self._inspect_dependencies(reg, active_di, payload_type)
        handler = self._wrap_dependencies(reg.handler, dependencies, active_di)
        handler = self._wrap_publishers(handler, reg.publish_to)
        return self._wrap_validated(handler, reg, payload_type)

    def _inspect_dependencies(
        self,
        reg: _Registration,
        di: DI,
        payload_type: type | None,
    ) -> tuple[_Dependency, ...]:
        del payload_type  # only used implicitly: first param is always the payload slot.
        deps = collect_dependencies(reg.handler, skip_first=True)
        for dep in deps:
            if not di.supports(dep.annotation, dep.default):
                ann_name = getattr(dep.annotation, "__name__", repr(dep.annotation))
                raise TypeError(
                    f"DI provider {di.name!r} cannot resolve parameter {dep.name!r}: "
                    f"{ann_name} (subscriber {reg.topic!r})",
                )
        return tuple(deps)

    def _wrap_validated(
        self,
        handler: Handler,
        reg: _Registration,
        payload_type: type | None,
    ) -> Handler:
        """Wrap `handler` so its first positional argument is the decoded payload.

        Pipeline for typed payloads:
            `native msg → codec.decode(bytes) → validator.decode(target_type) → handler`.

        For raw deliveries (handler annotated as :class:`Message`, no annotation, or a
        bytes-like type), the native message is wrapped in a :class:`Message` view that
        carries the subscriber-level codec, so the handler can call `msg.value` /
        `msg.decode(...)` without spelling out the codec each time.
        """
        codec = resolve_codec(reg.codec, fallback=self._default_codec)
        original = handler

        if payload_type is None or payload_type in _RAW_PAYLOAD_TYPES:

            async def wrapped_raw(msg: _NativeMessage) -> Any:
                return await original(Message(msg, codec))

            wrapped_raw.__wrapped__ = original  # type: ignore[attr-defined]
            return wrapped_raw

        validator = resolve_validator(payload_type)
        if validator is None:
            type_name = getattr(payload_type, "__name__", repr(payload_type))
            raise TypeError(
                f"no validator registered for {type_name!r} (subscriber {reg.topic!r}); "
                "register one via `register_validator` or install the matching extra",
            )

        async def wrapped(msg: _NativeMessage) -> Any:
            decoded = codec.decode(bytes(msg.payload))
            value = validator.decode(decoded, payload_type)
            return await original(value)

        wrapped.__wrapped__ = original  # type: ignore[attr-defined]
        return wrapped

    def _wrap_dependencies(
        self,
        handler: Handler,
        dependencies: Sequence[_Dependency],
        di: DI,
    ) -> Handler:
        """Wrap `handler` so DI-resolved values are appended after the payload argument."""
        if not dependencies:
            return handler
        original = handler
        deps = tuple(dependencies)
        context = self._context

        async def wrapped(payload: Any) -> Any:
            resolved: list[Any] = [
                await di.resolve(dep.annotation, context=context, default=dep.default)
                for dep in deps
            ]
            return await original(payload, *resolved)

        wrapped.__wrapped__ = original  # type: ignore[attr-defined]
        return wrapped

    def _wrap_publishers(
        self,
        handler: Handler,
        targets: Sequence[_PublishTarget],
    ) -> Handler:
        if not targets:
            return handler
        broker = self
        resolved: tuple[tuple[str, Codec], ...] = tuple(
            (target.topic, resolve_codec(target.codec, fallback=self._default_codec))
            for target in targets
        )

        async def wrapped(msg: _NativeMessage) -> Any:
            result = await handler(msg)
            if result is None:
                return None
            for topic, codec in resolved:
                payload = codec.encode(result)
                await broker._publish(topic, payload)
            return None

        wrapped.__wrapped__ = handler  # type: ignore[attr-defined]
        return wrapped

    async def _dispatch(
        self,
        subscriber: Subscriber,
        handler: Handler,
        topic: str,
    ) -> None:
        try:
            async for message in subscriber:
                await self._handle(message, handler, topic)
        except asyncio.CancelledError:
            subscriber.close()
            raise

    async def _handle(self, message: _NativeMessage, handler: Handler, topic: str) -> None:
        loop = asyncio.get_event_loop()
        self._metrics.record_received(topic)
        start = loop.time()
        async with self._context.enter_local(
            topic=topic,
            headers=dict(message.headers),
            raw_payload=bytes(message.payload),
        ):
            try:
                await handler(message)
            except Exception as exc:
                action = resolve_failure_action(self._on_error, exc)
                self._metrics.record_failure(topic, action, type(exc).__name__)
                logger.warning(
                    "handler raised %s on %s; applying %s",
                    exc,
                    topic,
                    action.value,
                )
                if action is FailureAction.RAISE:
                    raise
                with contextlib.suppress(RuntimeError):
                    if action is FailureAction.REQUEUE:
                        await message.nack(requeue=True)
                    elif action is FailureAction.ACK:
                        await message.ack()
                    else:  # FailureAction.NACK
                        await message.nack(requeue=False)
                return
            self._metrics.record_success(topic, loop.time() - start)
            with contextlib.suppress(RuntimeError):
                await message.ack()

    @abstractmethod
    async def _open(self) -> None:
        """Connect or initialise the underlying client. Called once by `start()`."""

    @abstractmethod
    async def _close(self) -> None:
        """Disconnect the underlying client. Called once by `stop()`."""

    @abstractmethod
    async def _subscribe(self, topic: str, **options: Any) -> Subscriber:
        """Open a single subscription on `topic`. Called per registration by `start()`.

        `options` carries the kwargs passed to `@broker.subscriber(topic, ...)`. Concrete
        brokers forward them to the native subscribe call.
        """

    @abstractmethod
    async def _publish(self, topic: str, payload: bytes) -> None:
        """Send one message to `topic`. Called by `publish()` and by `@publisher` wrappers."""


__all__: tuple[str, ...] = ("Broker", "Handler", "Router")
