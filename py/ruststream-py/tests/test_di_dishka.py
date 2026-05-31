"""End-to-end: handler dependency injection through DishkaDI."""

import asyncio
import dataclasses
from typing import Annotated

import pytest

pytest.importorskip("dishka")

from dishka import (
    AsyncContainer,
    FromComponent,
    FromDishka,
    Provider,
    Scope,
    make_async_container,
    provide,
)
from ruststream import ContextRepo, MemoryBroker, Message, RustStream
from ruststream.di import DIError, DishkaDI, MissingDependencyError

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Settings:
    name: str


class _AppProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return Settings(name="prod")

    @provide
    def secret(self) -> str:
        return "s3cret"


@pytest.fixture
def dishka_container() -> AsyncContainer:
    """Fresh Dishka `AsyncContainer` wired with `_AppProvider` at `Scope.APP`."""
    return make_async_container(_AppProvider())


@pytest.fixture
def dishka_broker(memory_broker_factory, dishka_container: AsyncContainer) -> MemoryBroker:
    """`MemoryBroker` whose DI is a `DishkaDI` backed by `dishka_container`."""
    return memory_broker_factory(di=DishkaDI(dishka_container))


async def test_dishka_resolves_from_dishka_marker(
    dishka_broker: MemoryBroker,
    wait_event,
) -> None:
    captured: list[Settings] = []
    seen = asyncio.Event()

    @dishka_broker.subscriber("t")
    async def handle(msg: Message, settings: FromDishka[Settings]) -> None:
        captured.append(settings)
        seen.set()

    async with RustStream(dishka_broker):
        await dishka_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [Settings(name="prod")]


async def test_dishka_resolves_context_repo_via_marker(
    dishka_broker: MemoryBroker,
    wait_event,
) -> None:
    captured: list[tuple[str, str]] = []
    seen = asyncio.Event()

    @dishka_broker.subscriber("t")
    async def handle(
        msg: Message,
        ctx: FromDishka[ContextRepo],
        token: FromDishka[str],
    ) -> None:
        captured.append((ctx.get_global("flag") or "unset", token))
        seen.set()

    app = RustStream(dishka_broker)
    app.context.set_global("flag", "lit")

    async with app:
        await dishka_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [("lit", "s3cret")]


async def test_dishka_resolves_explicit_annotated_form(
    dishka_broker: MemoryBroker,
    wait_event,
) -> None:
    """`Annotated[T, FromComponent()]` is the canonical explicit form Dishka recommends;
    `FromDishka[T]` is just a shortcut for the same shape."""
    captured: list[Settings] = []
    seen = asyncio.Event()

    @dishka_broker.subscriber("t")
    async def handle(
        msg: Message,
        settings: Annotated[Settings, FromComponent()],
    ) -> None:
        captured.append(settings)
        seen.set()

    async with RustStream(dishka_broker):
        await dishka_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [Settings(name="prod")]


async def test_dishka_rejects_bare_context_repo(dishka_broker: MemoryBroker) -> None:
    """Bare `ContextRepo` is a NoOpDI convenience; under DishkaDI users must opt in
    explicitly via `FromDishka[ContextRepo]`."""

    @dishka_broker.subscriber("t")
    async def handle(msg: Message, ctx: ContextRepo) -> None:
        pass

    with pytest.raises(TypeError, match="cannot resolve parameter 'ctx'"):
        async with RustStream(dishka_broker):
            await asyncio.sleep(0)


async def test_dishka_rejects_bare_annotation(dishka_broker: MemoryBroker) -> None:
    @dishka_broker.subscriber("t")
    async def handle(msg: Message, settings: Settings) -> None:
        pass

    with pytest.raises(TypeError, match="cannot resolve parameter 'settings'"):
        async with RustStream(dishka_broker):
            await asyncio.sleep(0)


async def test_dishka_resolve_unsupported_raises_dierror(
    dishka_container: AsyncContainer,
) -> None:
    di = DishkaDI(dishka_container)
    try:
        with pytest.raises(DIError, match="DishkaDI cannot resolve"):
            await di.resolve(int, context=ContextRepo())
    finally:
        await di.aclose()


async def test_dishka_aclose_closes_container(memory_broker_factory) -> None:
    class TrackingContainer:
        def __init__(self) -> None:
            self.close_calls = 0

        async def get(self, _target: type) -> object:
            raise AssertionError("get should not be called in this test")

        async def close(self) -> None:
            self.close_calls += 1

    container = TrackingContainer()
    broker = memory_broker_factory(di=DishkaDI(container))  # type: ignore[arg-type]

    async with RustStream(broker):
        await asyncio.sleep(0)

    assert container.close_calls == 1


async def test_dishka_missing_dependency_error_when_uninstalled(monkeypatch) -> None:
    """Forcing the import to fail surfaces a MissingDependencyError, not bare ImportError."""
    import sys

    real = sys.modules.get("dishka")
    monkeypatch.setitem(sys.modules, "dishka", None)
    try:
        with pytest.raises(MissingDependencyError):
            DishkaDI(real)  # type: ignore[arg-type]
    finally:
        if real is not None:
            monkeypatch.setitem(sys.modules, "dishka", real)
