"""End-to-end: handler signature introspection + codec + validator pipeline."""

import asyncio
import dataclasses
import importlib.util

import pytest
from ruststream import MemoryBroker, Message, RustStream
from ruststream.validators import Validator, register_validator

pytestmark = pytest.mark.asyncio


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


@dataclasses.dataclass
class Order:
    id: int
    name: str


@dataclasses.dataclass
class Address:
    city: str


@dataclasses.dataclass
class Person:
    name: str
    address: Address


async def test_dataclass_payload_decoded_via_codec_and_validator(
    memory_broker_json: MemoryBroker,
) -> None:
    received: list[Order] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("orders")
    async def handle(order: Order) -> None:
        received.append(order)
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("orders", {"id": 7, "name": "Order#7"})
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [Order(id=7, name="Order#7")]


async def test_nested_dataclass_payload(memory_broker_json: MemoryBroker) -> None:
    received: list[Person] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("people")
    async def handle(p: Person) -> None:
        received.append(p)
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("people", {"name": "x", "address": {"city": "y"}})
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [Person(name="x", address=Address(city="y"))]


async def test_message_first_param_bypasses_validator(memory_broker: MemoryBroker) -> None:
    received: list[bytes] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("raw")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("raw", b"hi")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [b"hi"]


async def test_subscriber_codec_override_used_for_decode(memory_broker: MemoryBroker) -> None:
    received: list[Order] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("orders", codec="json")
    async def handle(order: Order) -> None:
        received.append(order)
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("orders", {"id": 1, "name": "n"}, codec="json")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [Order(id=1, name="n")]


async def test_unknown_payload_type_raises_at_start(memory_broker_json: MemoryBroker) -> None:
    class NotRegistered:
        pass

    @memory_broker_json.subscriber("topic")
    async def handle(value: NotRegistered) -> None:
        pass

    with pytest.raises(TypeError, match="no validator registered"):
        async with RustStream(memory_broker_json):
            await asyncio.sleep(0)


async def test_custom_validator_routes_first_param(memory_broker: MemoryBroker) -> None:
    class Marker:
        def __init__(self, raw: bytes) -> None:
            self.raw = raw

        def __eq__(self, other: object) -> bool:
            return isinstance(other, Marker) and other.raw == self.raw

    class MarkerValidator(Validator):
        name = "marker"

        def supports(self, target_type: type) -> bool:
            return target_type is Marker

        def decode(self, data: object, target_type: type) -> object:
            del target_type
            if isinstance(data, (bytes, bytearray, memoryview)):
                return Marker(bytes(data))
            raise TypeError(f"unexpected type {type(data).__name__}")

        def encode(self, value: object) -> object:
            assert isinstance(value, Marker)
            return value.raw

        def json_schema(self, target_type: type) -> dict[str, object] | None:
            del target_type
            return None

    register_validator(MarkerValidator())
    received: list[Marker] = []
    seen = asyncio.Event()

    @memory_broker.subscriber("marker")
    async def handle(m: Marker) -> None:
        received.append(m)
        seen.set()

    async with RustStream(memory_broker):
        await memory_broker.publish("marker", b"hello")
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [Marker(b"hello")]


@pytest.mark.skipif(not _is_installed("pydantic"), reason="pydantic not installed")
async def test_pydantic_payload_round_trip(memory_broker_json: MemoryBroker) -> None:
    from pydantic import BaseModel

    class PydOrder(BaseModel):
        id: int
        name: str

    received: list[PydOrder] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("pyd")
    async def handle(order: PydOrder) -> None:
        received.append(order)
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("pyd", {"id": 3, "name": "p"})
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [PydOrder(id=3, name="p")]


@pytest.mark.skipif(not _is_installed("msgspec"), reason="msgspec not installed")
async def test_msgspec_payload_round_trip(memory_broker_json: MemoryBroker) -> None:
    import msgspec

    class MsgOrder(msgspec.Struct):
        id: int
        name: str

    received: list[MsgOrder] = []
    seen = asyncio.Event()

    @memory_broker_json.subscriber("msg")
    async def handle(order: MsgOrder) -> None:
        received.append(order)
        seen.set()

    async with RustStream(memory_broker_json):
        await memory_broker_json.publish("msg", {"id": 5, "name": "m"})
        await asyncio.wait_for(seen.wait(), timeout=1.0)

    assert received == [MsgOrder(id=5, name="m")]
