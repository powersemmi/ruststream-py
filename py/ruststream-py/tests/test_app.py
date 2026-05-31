"""Tests for the RustStream application aggregator."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest
from ruststream import ContextRepo, MemoryBroker, Message, RustStream


@pytest.mark.asyncio
async def test_app_runs_multiple_brokers_concurrently(
    memory_broker_factory: Callable[..., MemoryBroker],
) -> None:
    broker_a = memory_broker_factory()
    broker_b = memory_broker_factory()

    received: list[tuple[str, bytes]] = []
    both_seen = asyncio.Event()

    @broker_a.subscriber("topic.a")
    async def handle_a(msg: Message) -> None:
        received.append(("a", msg.payload))
        if any(tag == "b" for tag, _ in received):
            both_seen.set()

    @broker_b.subscriber("topic.b")
    async def handle_b(msg: Message) -> None:
        received.append(("b", msg.payload))
        if any(tag == "a" for tag, _ in received):
            both_seen.set()

    app = RustStream(title="test-app")
    app.add_broker(broker_a)
    app.add_broker(broker_b)
    assert len(app.brokers) == 2

    async with app:
        await asyncio.sleep(0.05)
        await broker_a.publish("topic.a", b"alpha")
        await broker_b.publish("topic.b", b"beta")
        await asyncio.wait_for(both_seen.wait(), timeout=1.0)

    assert {("a", b"alpha"), ("b", b"beta")}.issubset(set(received))


@pytest.mark.asyncio
async def test_lifespan_setup_runs_around_dispatch(memory_broker: MemoryBroker) -> None:
    seen = asyncio.Event()

    @memory_broker.subscriber("orders")
    async def handle(_msg: Message) -> None:
        seen.set()

    events: list[str] = []

    @asynccontextmanager
    async def lifespan(context: ContextRepo) -> AsyncIterator[None]:
        events.append("setup")
        context.set_global("rlm", "fake-resource-lock")
        yield
        events.append("teardown")
        assert context.get_global("rlm") == "fake-resource-lock"
        context.reset_global("rlm")

    app = RustStream(memory_broker, lifespan=lifespan)

    async with app:
        await asyncio.sleep(0.05)
        assert events == ["setup"]
        assert app.context.get_global("rlm") == "fake-resource-lock"
        await memory_broker.publish("orders", b"o-1")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert events == ["setup", "teardown"]
    assert app.context.get_global("rlm") is None


@pytest.mark.asyncio
async def test_lifespan_without_context_param(memory_broker: MemoryBroker) -> None:
    """A lifespan factory with no parameters runs without receiving the ContextRepo."""
    events: list[str] = []

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        events.append("setup")
        yield
        events.append("teardown")

    async with RustStream(memory_broker, lifespan=lifespan):
        await asyncio.sleep(0)

    assert events == ["setup", "teardown"]


@pytest.mark.asyncio
async def test_all_four_hooks_and_lifespan_fire_in_order(memory_broker: MemoryBroker) -> None:
    order: list[str] = []

    @asynccontextmanager
    async def lifespan(_ctx: ContextRepo) -> AsyncIterator[None]:
        order.append("lifespan-enter")
        yield
        order.append("lifespan-exit")

    app = RustStream(memory_broker, lifespan=lifespan)

    @app.on_startup
    async def on_startup_hook() -> None:
        order.append("on_startup")

    @app.after_startup
    async def after_startup_hook() -> None:
        order.append("after_startup")

    @app.on_shutdown
    async def on_shutdown_hook() -> None:
        order.append("on_shutdown")

    @app.after_shutdown
    async def after_shutdown_hook() -> None:
        order.append("after_shutdown")

    async with app:
        await asyncio.sleep(0.01)

    assert order == [
        "on_startup",
        "lifespan-enter",
        "after_startup",
        "on_shutdown",
        "lifespan-exit",
        "after_shutdown",
    ]


@pytest.mark.asyncio
async def test_lifespan_wraps_outside_brokers_and_hooks_see_running_brokers(
    memory_broker: MemoryBroker,
) -> None:
    """Lifespan setup runs BEFORE broker.start (so publishing from there is unsafe), and
    lifespan teardown runs AFTER broker.stop (same restriction). Conversely,
    ``after_startup`` and ``on_shutdown`` execute while brokers are live, which is why
    they are the right place for warm-up publishes or graceful farewells.
    """
    snapshots: dict[str, bool] = {}

    def running() -> bool:
        return bool(getattr(memory_broker, "_started", False))

    @asynccontextmanager
    async def lifespan(_ctx: ContextRepo) -> AsyncIterator[None]:
        snapshots["lifespan_setup"] = running()
        yield
        snapshots["lifespan_teardown"] = running()

    app = RustStream(memory_broker, lifespan=lifespan)

    @app.after_startup
    async def grab_after_startup() -> None:
        snapshots["after_startup"] = running()

    @app.on_shutdown
    async def grab_on_shutdown() -> None:
        snapshots["on_shutdown"] = running()

    async with app:
        await asyncio.sleep(0.01)

    assert snapshots == {
        "lifespan_setup": False,
        "after_startup": True,
        "on_shutdown": True,
        "lifespan_teardown": False,
    }


@pytest.mark.asyncio
async def test_multiple_hooks_run_in_registration_order() -> None:
    app = RustStream()
    order: list[str] = []

    @app.on_startup
    async def first() -> None:
        order.append("first")

    @app.on_startup
    async def second() -> None:
        order.append("second")

    @app.on_startup
    async def third() -> None:
        order.append("third")

    async with app:
        await asyncio.sleep(0.01)

    assert order == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_hooks_receive_context_when_declared() -> None:
    app = RustStream()
    seen_values: list[object] = []

    @app.on_startup
    async def writes(context: ContextRepo) -> None:
        context.set_global("flag", "set-in-startup")

    @app.after_startup
    async def reads(context: ContextRepo) -> None:
        seen_values.append(context.get_global("flag"))

    @app.on_shutdown
    async def reads_again(context: ContextRepo) -> None:
        seen_values.append(context.get_global("flag"))

    async with app:
        await asyncio.sleep(0.01)

    assert seen_values == ["set-in-startup", "set-in-startup"]


@pytest.mark.asyncio
async def test_hooks_without_parameters_are_called_with_no_arguments() -> None:
    app = RustStream()
    calls = 0

    @app.on_startup
    async def no_args() -> None:
        nonlocal calls
        calls += 1

    async with app:
        await asyncio.sleep(0.01)

    assert calls == 1


@pytest.mark.asyncio
async def test_startup_hook_failure_aborts_run() -> None:
    app = RustStream()

    @app.on_startup
    async def bad_startup() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await app.run()


@pytest.mark.asyncio
async def test_after_startup_failure_aborts_run(memory_broker: MemoryBroker) -> None:
    app = RustStream(memory_broker)

    @app.after_startup
    async def bad_after_startup() -> None:
        raise RuntimeError("after-startup-boom")

    with pytest.raises(RuntimeError, match="after-startup-boom"):
        await app.run()


@pytest.mark.asyncio
async def test_shutdown_side_hook_failures_are_logged_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = RustStream()
    after_shutdown_called = asyncio.Event()

    @app.on_shutdown
    async def bad_on_shutdown() -> None:
        raise RuntimeError("on-shutdown-boom")

    @app.after_shutdown
    async def good_after_shutdown() -> None:
        after_shutdown_called.set()

    with caplog.at_level("ERROR"):
        async with app:
            await asyncio.sleep(0.01)

    assert after_shutdown_called.is_set()
    assert any("on_shutdown" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_lifespan_resolves_dependency_via_app_di(memory_broker: MemoryBroker) -> None:
    """App-level DI feeds the lifespan factory the same way as it feeds handlers."""

    class _StaticDI:
        name = "static"

        def supports(self, annotation: object, default: object) -> bool:
            del default
            return annotation is str or annotation is ContextRepo

        async def resolve(
            self,
            annotation: object,
            *,
            context: ContextRepo,
            default: object = None,
        ) -> object:
            del default
            if annotation is str:
                return "from-di"
            return context

        async def aclose(self) -> None:
            return None

    captured: list[tuple[str, str]] = []

    @asynccontextmanager
    async def lifespan(ctx: ContextRepo, label: str) -> AsyncIterator[None]:
        captured.append(("enter", label))
        ctx.set_global("label", label)
        yield
        captured.append(("exit", label))

    app = RustStream(memory_broker, lifespan=lifespan, di=_StaticDI())  # type: ignore[arg-type]
    async with app:
        assert app.context.get_global("label") == "from-di"

    assert captured == [("enter", "from-di"), ("exit", "from-di")]


@pytest.mark.asyncio
async def test_hooks_resolve_dependencies_via_app_di(memory_broker: MemoryBroker) -> None:
    """Lifecycle hooks share the same DI-driven binding as the lifespan factory."""

    class _StaticDI:
        name = "static"

        def supports(self, annotation: object, default: object) -> bool:
            del default
            return annotation is int or annotation is ContextRepo

        async def resolve(
            self,
            annotation: object,
            *,
            context: ContextRepo,
            default: object = None,
        ) -> object:
            del default
            if annotation is int:
                return 42
            return context

        async def aclose(self) -> None:
            return None

    seen: list[tuple[str, int | str]] = []

    app = RustStream(memory_broker, di=_StaticDI())  # type: ignore[arg-type]

    @app.on_startup
    async def boot(ctx: ContextRepo, n: int) -> None:
        seen.append(("startup", n))
        ctx.set_global("n", n)

    @app.after_shutdown
    async def done() -> None:
        seen.append(("done", "no-deps"))

    async with app:
        await asyncio.sleep(0)

    assert seen == [("startup", 42), ("done", "no-deps")]
    assert app.context.get_global("n") == 42


@pytest.mark.asyncio
async def test_lifespan_unresolved_dependency_raises(memory_broker: MemoryBroker) -> None:
    """Under the default NoOpDI a lifespan factory requesting a non-context type fails."""

    @asynccontextmanager
    async def lifespan(_db: int) -> AsyncIterator[None]:
        yield

    app = RustStream(memory_broker, lifespan=lifespan)
    with pytest.raises(TypeError, match="cannot resolve lifespan parameter '_db'"):
        async with app:
            await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_app_di_aclose_runs_on_shutdown(memory_broker: MemoryBroker) -> None:
    close_called = asyncio.Event()

    class _TrackedDI:
        name = "tracked"

        def supports(self, annotation: object, default: object) -> bool:
            del default
            return annotation is ContextRepo

        async def resolve(
            self,
            annotation: object,
            *,
            context: ContextRepo,
            default: object = None,
        ) -> object:
            del annotation, default
            return context

        async def aclose(self) -> None:
            close_called.set()

    async with RustStream(memory_broker, di=_TrackedDI()):  # type: ignore[arg-type]
        await asyncio.sleep(0)

    assert close_called.is_set()


@pytest.mark.asyncio
async def test_shutdown_outside_context_manager(memory_broker: MemoryBroker) -> None:
    seen = asyncio.Event()

    @memory_broker.subscriber("orders")
    async def handle(_msg: Message) -> None:
        seen.set()

    app = RustStream(memory_broker)

    run_task = asyncio.create_task(app.run())
    await asyncio.sleep(0.05)
    await memory_broker.publish("orders", b"order-1")
    await asyncio.wait_for(seen.wait(), timeout=1.0)

    app.shutdown()
    try:
        await asyncio.wait_for(run_task, timeout=1.0)
    except asyncio.CancelledError:
        pass
    except BaseExceptionGroup as group:
        for exc in group.exceptions:
            if not isinstance(exc, asyncio.CancelledError):
                raise
