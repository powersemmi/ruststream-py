"""End-to-end: handler dependency injection through FastDependsDI."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

import pytest

pytest.importorskip("fast_depends")

from fast_depends import Depends
from ruststream import ContextRepo, MemoryBroker, Message, RustStream
from ruststream.di import Context, DIError, FastDependsDI, MissingDependencyError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fastdepends_broker(memory_broker_factory) -> MemoryBroker:
    """`MemoryBroker` whose DI provider is a fresh `FastDependsDI`."""
    return memory_broker_factory(di=FastDependsDI())


def _get_token_sync() -> str:
    return "t0"


async def _get_token_async() -> str:
    await asyncio.sleep(0)
    return "async"


def _get_prefix() -> str:
    return "pre"


def _get_full(prefix: str = Depends(_get_prefix)) -> str:
    return f"{prefix}/full"


@pytest.mark.parametrize(
    ("depender", "expected"),
    [
        pytest.param(_get_token_sync, "t0", id="sync"),
        pytest.param(_get_token_async, "async", id="async"),
        pytest.param(_get_full, "pre/full", id="nested"),
    ],
)
async def test_fastdepends_resolves_dependers(
    fastdepends_broker: MemoryBroker,
    wait_event,
    depender: Callable[..., str] | Callable[..., Awaitable[str]],
    expected: str,
) -> None:
    captured: list[str] = []
    seen = asyncio.Event()

    @fastdepends_broker.subscriber("t")
    async def handle(msg: Message, value: str = Depends(depender)) -> None:
        captured.append(value)
        seen.set()

    async with RustStream(fastdepends_broker):
        await fastdepends_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [expected]


async def test_fastdepends_resolves_context_via_marker(
    fastdepends_broker: MemoryBroker,
    wait_event,
) -> None:
    def get_value() -> int:
        return 99

    captured: list[tuple[str, int]] = []
    seen = asyncio.Event()

    @fastdepends_broker.subscriber("t")
    async def handle(
        msg: Message,
        ctx: ContextRepo = Depends(Context),
        value: int = Depends(get_value),
    ) -> None:
        captured.append((ctx.get_global("tag") or "unset", value))
        seen.set()

    app = RustStream(fastdepends_broker)
    app.context.set_global("tag", "ready")

    async with app:
        await fastdepends_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [("ready", 99)]


async def test_fastdepends_resolves_annotated_form(
    fastdepends_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    """`Annotated[T, Depends(callable)]` is the alternative no-default form supported
    by fast-depends; both placements of the marker resolve identically."""

    def get_token() -> str:
        return "t-annotated"

    captured: list[str] = []
    seen = asyncio.Event()

    @fastdepends_broker.subscriber("t")
    async def handle(msg: Message, token: Annotated[str, Depends(get_token)]) -> None:
        captured.append(token)
        seen.set()

    async with RustStream(fastdepends_broker):
        await fastdepends_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == ["t-annotated"]


async def test_fastdepends_resolves_context_via_annotated_marker(
    fastdepends_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    """`Annotated[ContextRepo, Depends(Context)]` reaches the same sentinel branch as
    the default-form `ctx: ContextRepo = Depends(Context)`."""
    captured: list[bool] = []
    seen = asyncio.Event()

    @fastdepends_broker.subscriber("t")
    async def handle(
        msg: Message,
        ctx: Annotated[ContextRepo, Depends(Context)],
    ) -> None:
        captured.append(ctx.get_global("flag") == "lit")
        seen.set()

    app = RustStream(fastdepends_broker)
    app.context.set_global("flag", "lit")

    async with app:
        await fastdepends_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [True]


async def test_fastdepends_rejects_bare_context_repo(
    fastdepends_broker: MemoryBroker,
) -> None:
    """Bare `ContextRepo` is a NoOpDI convenience; under FastDependsDI users must opt
    in explicitly via `Depends(Context)`."""

    @fastdepends_broker.subscriber("t")
    async def handle(msg: Message, ctx: ContextRepo) -> None:
        pass

    with pytest.raises(TypeError, match="cannot resolve parameter 'ctx'"):
        async with RustStream(fastdepends_broker):
            await asyncio.sleep(0)


async def test_fastdepends_rejects_param_without_depends(
    fastdepends_broker: MemoryBroker,
) -> None:
    @fastdepends_broker.subscriber("t")
    async def handle(msg: Message, value: int) -> None:
        pass

    with pytest.raises(TypeError, match="cannot resolve parameter 'value'"):
        async with RustStream(fastdepends_broker):
            await asyncio.sleep(0)


def test_context_sentinel_raises_when_called_directly() -> None:
    """Calling `Context()` outside a `Depends(...)` is a programmer error."""
    with pytest.raises(RuntimeError, match="FastDependsDI sentinel"):
        Context()


async def test_fastdepends_resolve_without_marker_raises_dierror() -> None:
    di = FastDependsDI()
    with pytest.raises(DIError, match="FastDependsDI cannot resolve"):
        await di.resolve(int, context=ContextRepo())


async def test_fastdepends_missing_dependency_error_when_uninstalled(monkeypatch) -> None:
    import sys

    real = sys.modules.get("fast_depends")
    monkeypatch.setitem(sys.modules, "fast_depends", None)
    try:
        with pytest.raises(MissingDependencyError):
            FastDependsDI()
    finally:
        if real is not None:
            monkeypatch.setitem(sys.modules, "fast_depends", real)
