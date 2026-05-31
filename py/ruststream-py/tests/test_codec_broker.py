"""End-to-end: Broker codec defaults, @publisher codec, broker.publish(value, codec=...)."""

import asyncio
from collections.abc import Callable

import pytest
from ruststream import MemoryBroker, MemoryRouter, Message, RustStream
from ruststream.codecs import CodecError, JsonCodec

pytestmark = pytest.mark.asyncio


async def test_broker_default_codec_applies_to_publish(memory_broker_json: MemoryBroker) -> None:
    received: list[bytes] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {"id": 1, "name": "Order#1"})
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b'{"id":1,"name":"Order#1"}']


async def test_publish_codec_override_takes_precedence(memory_broker: MemoryBroker) -> None:
    received: list[bytes] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("events")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("events", {"k": "v"}, codec="json")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b'{"k":"v"}']


async def test_publish_with_raw_default_rejects_dict(memory_broker: MemoryBroker) -> None:
    with pytest.raises(CodecError, match="bytes-like"):
        await memory_broker.publish("topic", {"k": "v"})


async def test_publisher_decorator_encodes_through_broker_default(
    memory_broker_json: MemoryBroker,
) -> None:
    responses: list[bytes] = []
    response_seen = asyncio.Event()

    @memory_broker_json.subscriber("requests")
    @memory_broker_json.publisher("responses")
    async def handle_request(_msg: Message) -> dict[str, str]:
        return {"reply_to": "hello"}

    @memory_broker_json.subscriber("responses")
    async def handle_response(msg: Message) -> None:
        responses.append(bytes(msg.payload))
        response_seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("requests", {"payload": "hello"})
        await asyncio.wait_for(response_seen.wait(), timeout=1.0)

    assert responses == [b'{"reply_to":"hello"}']


async def test_publisher_codec_override_per_topic(memory_broker: MemoryBroker) -> None:
    seen = asyncio.Event()
    received: list[bytes] = []

    @memory_broker.subscriber("input")
    @memory_broker.publisher("output", codec="json")
    async def handle(_msg: Message) -> dict[str, int]:
        return {"count": 42}

    @memory_broker.subscriber("output")
    async def collect(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("input", b"trigger")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b'{"count":42}']


async def test_router_publisher_inherits_broker_codec_at_attach_time(
    memory_broker_json: MemoryBroker,
    memory_router: MemoryRouter,
) -> None:
    seen = asyncio.Event()
    received: list[bytes] = []

    @memory_router.subscriber("req")
    @memory_router.publisher("resp")
    async def handle(_msg: Message) -> dict[str, str]:
        return {"status": "ok"}

    @memory_router.subscriber("resp")
    async def collect(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    memory_broker_json.include_router(memory_router)

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("req", {"go": True})
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b'{"status":"ok"}']


async def test_codec_instance_accepted_directly(
    memory_broker_factory: Callable[..., MemoryBroker],
) -> None:
    broker = memory_broker_factory(codec=JsonCodec())
    received: list[bytes] = []
    seen = asyncio.Event()

    @broker.subscriber("topic")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(broker):
        await broker.publish("topic", [1, 2, 3])
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b"[1,2,3]"]


async def test_backwards_compat_raw_bytes_publish(memory_broker: MemoryBroker) -> None:
    """Existing user code `broker.publish("topic", b"bytes")` still works with raw default."""
    received: list[bytes] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("legacy")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("legacy", b"raw-payload")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b"raw-payload"]
