"""End-to-end test: MemoryBroker decorator API + RustStream lifecycle."""

import asyncio

import pytest
from ruststream import MemoryBroker, MemoryRouter, Message, RustStream


@pytest.mark.asyncio
async def test_handler_receives_published_message(memory_broker: MemoryBroker) -> None:
    received: list[bytes] = []
    handler_called = asyncio.Event()

    @memory_broker.subscriber("orders")
    async def handle(msg: Message) -> None:
        received.append(msg.payload)
        handler_called.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("orders", b"order-1")
        await asyncio.wait_for(handler_called.wait(), timeout=1.0)

    assert received == [b"order-1"]


@pytest.mark.asyncio
async def test_router_decorator_attaches_to_broker(
    memory_broker: MemoryBroker,
    memory_router: MemoryRouter,
) -> None:
    received: list[bytes] = []
    seen = asyncio.Event()

    @memory_router.subscriber("events")
    async def handle(msg: Message) -> None:
        received.append(msg.payload)
        seen.set()

    memory_broker.include_router(memory_router)

    async with RustStream(memory_broker):
        await memory_broker.publish("events", b"event-1")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b"event-1"]


@pytest.mark.asyncio
async def test_publisher_decorator_auto_publishes_return_value(
    memory_broker: MemoryBroker,
) -> None:
    responses: list[bytes] = []
    response_seen = asyncio.Event()

    @memory_broker.subscriber("requests")
    @memory_broker.publisher("responses")
    async def handle_request(msg: Message) -> bytes:
        return b"reply-to-" + bytes(msg.payload)

    @memory_broker.subscriber("responses")
    async def handle_response(msg: Message) -> None:
        responses.append(msg.payload)
        response_seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("requests", b"req-1")
        await asyncio.wait_for(response_seen.wait(), timeout=1.0)

    assert responses == [b"reply-to-req-1"]


@pytest.mark.asyncio
async def test_handler_exception_triggers_nack(memory_broker: MemoryBroker) -> None:
    attempts = 0
    seen = asyncio.Event()

    @memory_broker.subscriber("events")
    async def handle(_msg: Message) -> None:
        nonlocal attempts
        attempts += 1
        seen.set()
        raise RuntimeError("simulated failure")

    async with RustStream(memory_broker):
        await memory_broker.publish("events", b"event-1")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert attempts == 1


@pytest.mark.asyncio
async def test_publish_batch_delivers_every_message_in_order(
    memory_broker: MemoryBroker,
) -> None:
    received: list[bytes] = []
    all_seen = asyncio.Event()
    expected = [f"m{i}".encode() for i in range(10)]

    @memory_broker.subscriber("batch")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        if len(received) == len(expected):
            all_seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish_batch("batch", expected)
        await asyncio.wait_for(all_seen.wait(), timeout=1.0)

    assert received == expected


@pytest.mark.asyncio
async def test_publish_batch_encodes_each_value_with_codec(
    memory_broker_json: MemoryBroker,
) -> None:
    received: list[dict[str, int]] = []
    all_seen = asyncio.Event()
    payloads = [{"n": 1}, {"n": 2}, {"n": 3}]

    @memory_broker_json.subscriber("batch.json")
    async def handle(msg: Message) -> None:
        received.append(msg.decode())
        if len(received) == len(payloads):
            all_seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish_batch("batch.json", payloads)
        await asyncio.wait_for(all_seen.wait(), timeout=1.0)

    assert received == payloads
