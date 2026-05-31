"""End-to-end: handler dependency injection via NoOpDI (ContextRepo-only)."""

import asyncio
import dataclasses
import inspect
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from ruststream import ContextRepo, MemoryBroker, Message, NoOpDI, RustStream
from ruststream.di import DI, DIError

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Order:
    id: int
    name: str


def make_static_di(
    name: str,
    *,
    supports_type: type,
    value: Any | None = None,
    return_context: bool = False,
    on_close: Callable[[], None] | None = None,
) -> DI:
    """Build a single-purpose DI that resolves one annotation to a fixed value.

    `value` is what `resolve()` returns when `return_context` is False; otherwise the
    broker's `ContextRepo` is returned (used to assert `aclose` runs without faking
    `supports`). `on_close` lets the caller observe `aclose` invocation.
    """

    class _StaticDI(DI):
        def __init__(self) -> None:
            self.name = name

        def supports(self, annotation: object, default: object) -> bool:
            del default
            return annotation is supports_type

        async def resolve(
            self,
            annotation: object,
            *,
            context: ContextRepo,
            default: object = inspect.Parameter.empty,
        ) -> object:
            del annotation, default
            if return_context:
                return context
            return value

        async def aclose(self) -> None:
            if on_close is not None:
                on_close()

    return _StaticDI()


async def test_handler_can_request_context_via_noop_di(
    memory_broker_json: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    seen = asyncio.Event()
    captured: list[str] = []

    @memory_broker_json.subscriber("orders")
    async def handle(order: Order, ctx: ContextRepo) -> None:
        ctx.set_global("last_order", order)
        captured.append(ctx.get_global("config") or "no-config")
        seen.set()

    app = RustStream(memory_broker_json)
    app.context.set_global("config", "from-app")

    async with app:
        await memory_broker_json.publish("orders", {"id": 1, "name": "n"})
        await wait_event(seen)

    assert app.context.get_global("last_order") == Order(id=1, name="n")
    assert captured == ["from-app"]


async def test_message_handler_can_also_request_context(
    memory_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    captured: list[str] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("topic")
    async def handle(msg: Message, ctx: ContextRepo) -> None:
        captured.append(ctx.get_global("flag") or "unset")
        captured.append(bytes(msg.payload).decode())
        seen.set()

    app = RustStream(memory_broker)
    app.context.set_global("flag", "lit")

    async with app:
        await memory_broker.publish("topic", b"raw")
        await wait_event(seen)

    assert captured == ["lit", "raw"]


async def test_handler_without_context_param_works_unchanged(
    memory_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    received: list[bytes] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("plain")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("plain", b"hi")
        await wait_event(seen)

    assert received == [b"hi"]


async def test_noop_di_rejects_non_context_dependency(memory_broker: MemoryBroker) -> None:
    class Database:
        pass

    @memory_broker.subscriber("topic")
    async def handle(msg: Message, db: Database) -> None:
        pass

    with pytest.raises(TypeError, match="cannot resolve parameter 'db'"):
        async with RustStream(memory_broker):
            await asyncio.sleep(0)


async def test_broker_level_di_override_is_used(
    memory_broker_factory: Callable[..., MemoryBroker],
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    broker = memory_broker_factory(
        di=make_static_di("custom", supports_type=str, value="injected-string"),
    )
    captured: list[str] = []
    seen = asyncio.Event()

    @broker.subscriber("t")
    async def handle(msg: Message, flag: str) -> None:
        captured.append(flag)
        seen.set()

    async with RustStream(broker):
        await broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == ["injected-string"]


async def test_subscriber_level_di_override(
    memory_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    captured: list[str] = []
    seen = asyncio.Event()

    @memory_broker.subscriber(
        "t",
        di=make_static_di("strings", supports_type=str, value="per-subscriber"),
    )
    async def with_string(msg: Message, value: str) -> None:
        captured.append(value)
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == ["per-subscriber"]


async def test_noop_di_resolve_unknown_type_raises_di_error() -> None:
    di = NoOpDI()
    with pytest.raises(DIError, match="NoOpDI cannot resolve"):
        await di.resolve(int, context=ContextRepo())


async def test_di_aclose_called_on_broker_stop(
    memory_broker_factory: Callable[..., MemoryBroker],
) -> None:
    close_called = asyncio.Event()
    broker = memory_broker_factory(
        di=make_static_di(
            "tracked",
            supports_type=ContextRepo,
            return_context=True,
            on_close=close_called.set,
        ),
    )

    async with RustStream(broker):
        await asyncio.sleep(0)

    assert close_called.is_set()
