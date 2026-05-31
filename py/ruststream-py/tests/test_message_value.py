"""Coverage for `Message.value` / `Message.decode(...)` codec helpers."""

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable

import pytest
from ruststream import MemoryBroker, Message, RustStream

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Order:
    id: int
    name: str


async def test_value_returns_decoded_payload_via_subscriber_codec(
    memory_broker_json: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    captured: list[object] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(msg: Message) -> None:
        captured.append(msg.value)
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {"id": 7, "name": "x"})
        await wait_event(seen)

    assert captured == [{"id": 7, "name": "x"}]


async def test_value_is_cached_across_reads(
    memory_broker_json: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    """Repeated `.value` accesses on the same delivery decode only once."""
    snapshots: list[bool] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(msg: Message) -> None:
        first = msg.value
        second = msg.value
        snapshots.append(first is second)
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {"k": "v"})
        await wait_event(seen)

    assert snapshots == [True]


async def test_decode_with_target_type_routes_through_validator(
    memory_broker_json: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    decoded: list[Order] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(msg: Message) -> None:
        decoded.append(msg.decode(Order))
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {"id": 1, "name": "n"})
        await wait_event(seen)

    assert decoded == [Order(id=1, name="n")]


async def test_decode_without_target_returns_raw_codec_output(
    memory_broker_json: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    captured: list[object] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(msg: Message) -> None:
        captured.append(msg.decode())
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {"k": 1})
        await wait_event(seen)

    assert captured == [{"k": 1}]


async def test_decode_unknown_target_type_raises_type_error(
    memory_broker_json: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    class NotRegistered:
        pass

    errors: list[TypeError] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(msg: Message) -> None:
        try:
            msg.decode(NotRegistered)
        except TypeError as exc:
            errors.append(exc)
        finally:
            seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {})
        await wait_event(seen)

    assert len(errors) == 1
    assert "no validator registered" in str(errors[0])


async def test_subscriber_codec_override_drives_value(
    memory_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    """Per-subscriber codec wins over the broker default for `.value` decoding."""
    captured: list[object] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("orders", codec="json")
    async def handle(msg: Message) -> None:
        captured.append(msg.value)
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("orders", {"k": "v"}, codec="json")
        await wait_event(seen)

    assert captured == [{"k": "v"}]


async def test_payload_and_headers_proxy_through_to_native(
    memory_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    """The wrapper exposes the same byte-level payload and headers as the native delivery."""
    seen = asyncio.Event()
    captured: list[bytes] = []

    @memory_broker.subscriber("topic")
    async def handle(msg: Message) -> None:
        captured.append(bytes(msg.payload))
        assert isinstance(msg.headers, dict | type({}))
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("topic", b"raw-bytes")
        await wait_event(seen)

    assert captured == [b"raw-bytes"]
