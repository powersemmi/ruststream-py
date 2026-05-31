"""AsyncAPI spec generation, serialization, and viewer rendering."""

import dataclasses
import importlib.util
import json
import sys
from typing import Any

import pytest
from ruststream import MemoryBroker, MemoryRouter, Message, RustStream
from ruststream.asyncapi import (
    AsyncAPIError,
    MissingDependencyError,
    build_spec,
    build_spec_for_router,
    render_viewer_html,
    to_json,
    to_yaml,
)
from ruststream.asyncapi._viewer import DEFAULT_CSS_URL, DEFAULT_REACT_URL


@dataclasses.dataclass
class Order:
    id: int
    name: str


def _has_yaml() -> bool:
    return importlib.util.find_spec("yaml") is not None


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


def test_build_spec_minimal_shape_for_empty_broker(memory_broker: MemoryBroker) -> None:
    spec = build_spec(memory_broker, title="empty", version="9.9.9")
    assert spec["asyncapi"].startswith("3.")
    assert spec["info"] == {"title": "empty", "version": "9.9.9"}
    assert spec["channels"] == {}
    assert spec["operations"] == {}
    assert spec["components"] == {"messages": {}, "schemas": {}}


def test_build_spec_records_message_handler_without_payload_schema(
    memory_broker: MemoryBroker,
) -> None:
    @memory_broker.subscriber("orders.raw")
    async def handle(_msg: Message) -> None:
        pass

    spec = build_spec(memory_broker)
    assert "orders_raw" in spec["channels"]
    assert spec["channels"]["orders_raw"]["address"] == "orders.raw"
    assert "receive_orders_raw" in spec["operations"]
    assert spec["operations"]["receive_orders_raw"]["action"] == "receive"
    assert spec["components"]["schemas"] == {}


def test_build_spec_emits_validator_schema_for_typed_payload(
    memory_broker_json: MemoryBroker,
) -> None:
    @memory_broker_json.subscriber("orders.typed")
    async def handle(_order: Order) -> None:
        pass

    spec = build_spec(memory_broker_json)
    schemas = spec["components"]["schemas"]
    assert "Order" in schemas
    payload_msg = spec["components"]["messages"]["orders_typed_payload"]
    assert payload_msg["payload"] == {"$ref": "#/components/schemas/Order"}


def test_build_spec_includes_publisher_send_operation(memory_broker: MemoryBroker) -> None:
    @memory_broker.subscriber("input")
    @memory_broker.publisher("output")
    async def handle(_msg: Message) -> None:
        pass

    spec = build_spec(memory_broker)
    assert "receive_input" in spec["operations"]
    send_op = spec["operations"]["send_output"]
    assert send_op["action"] == "send"
    assert send_op["channel"] == {"$ref": "#/channels/output"}


def test_build_spec_for_router_works_standalone(memory_router: MemoryRouter) -> None:
    @memory_router.subscriber("router.topic")
    async def handle(_msg: Message) -> None:
        pass

    spec = build_spec_for_router(memory_router, title="router", version="0.1.0")
    assert spec["channels"]["router_topic"]["address"] == "router.topic"
    assert spec["operations"]["receive_router_topic"]["action"] == "receive"


def test_build_spec_merges_brokers_from_app(
    memory_broker: MemoryBroker,
    memory_broker_factory: Any,
) -> None:
    other = memory_broker_factory()

    @memory_broker.subscriber("a")
    async def handle_a(_msg: Message) -> None:
        pass

    @other.subscriber("b")
    async def handle_b(_msg: Message) -> None:
        pass

    app = RustStream(memory_broker)
    app.add_broker(other)
    spec = build_spec(app)
    assert {"a", "b"} == {spec["channels"][cid]["address"] for cid in spec["channels"]}
    assert {"receive_a", "receive_b"}.issubset(spec["operations"].keys())


def test_to_json_round_trips_through_stdlib_json(memory_broker: MemoryBroker) -> None:
    spec = build_spec(memory_broker, title="json-roundtrip")
    text = to_json(spec)
    assert json.loads(text)["info"]["title"] == "json-roundtrip"


@pytest.mark.skipif(not _has_yaml(), reason="PyYAML not installed")
def test_to_yaml_serializes_when_dependency_present(memory_broker: MemoryBroker) -> None:
    import yaml

    spec = build_spec(memory_broker, title="yaml")
    text = to_yaml(spec)
    assert yaml.safe_load(text)["info"]["title"] == "yaml"


def test_to_yaml_raises_missing_dependency_when_yaml_absent(
    memory_broker: MemoryBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "yaml", None)
    with pytest.raises(MissingDependencyError, match="asyncapi"):
        to_yaml(build_spec(memory_broker))


def test_render_viewer_html_inlines_spec_url_and_default_cdn() -> None:
    page = render_viewer_html("https://example.com/asyncapi.json", title="My Service")
    assert "https://example.com/asyncapi.json" in page
    assert "My Service" in page
    assert DEFAULT_REACT_URL in page
    assert DEFAULT_CSS_URL in page


def test_render_viewer_html_escapes_user_supplied_values() -> None:
    page = render_viewer_html(
        'https://example.com/"><script>alert(1)</script>',
        title="<title>",
    )
    assert "<script>alert(1)</script>" not in page
    assert "&lt;title&gt;" in page


def test_async_api_error_hierarchy() -> None:
    assert issubclass(MissingDependencyError, AsyncAPIError)


def test_subscriber_codec_sets_message_content_type(memory_broker: MemoryBroker) -> None:
    """Per-subscriber codec overrides the broker default in the resulting `contentType`."""

    @memory_broker.subscriber("a", codec="json")
    async def handle_a(_msg: Message) -> None:
        pass

    @memory_broker.subscriber("b")
    async def handle_b(_msg: Message) -> None:
        pass

    spec = build_spec(memory_broker)
    messages = spec["components"]["messages"]
    assert messages["a_payload"]["contentType"] == "application/json"
    assert messages["b_payload"]["contentType"] == "application/octet-stream"


def test_publisher_codec_overrides_default_content_type(memory_broker: MemoryBroker) -> None:
    @memory_broker.subscriber("in")
    @memory_broker.publisher("out", codec="json")
    async def handle(_msg: Message) -> None:
        pass

    spec = build_spec(memory_broker)
    assert spec["components"]["messages"]["out_payload"]["contentType"] == "application/json"


@pytest.mark.skipif(not _is_installed("pydantic"), reason="pydantic not installed")
def test_pydantic_defs_hoisted_to_components_schemas(
    memory_broker_json: MemoryBroker,
) -> None:
    """Nested Pydantic models live in `$defs` upstream; the builder hoists them."""
    from pydantic import BaseModel

    class Address(BaseModel):
        city: str

    class PydOrder(BaseModel):
        id: int
        address: Address

    @memory_broker_json.subscriber("orders")
    async def handle(_o: PydOrder) -> None:
        pass

    spec = build_spec(memory_broker_json)
    schemas = spec["components"]["schemas"]
    assert "PydOrder" in schemas
    assert "Address" in schemas
    address_ref = schemas["PydOrder"]["properties"]["address"]["$ref"]
    assert address_ref == "#/components/schemas/Address"
    assert "$defs" not in schemas["PydOrder"]


@pytest.mark.skipif(not _is_installed("msgspec"), reason="msgspec not installed")
def test_msgspec_top_level_ref_is_unwrapped(
    memory_broker_json: MemoryBroker,
) -> None:
    """msgspec returns `{"$ref": "#/$defs/Order", "$defs": {...}}`. The hoist step
    pulls every entry into components.schemas and resolves the message payload to
    the named schema rather than a redundant alias wrapper."""
    import msgspec

    class Address(msgspec.Struct):
        city: str

    class MsgOrder(msgspec.Struct):
        id: int
        address: Address

    @memory_broker_json.subscriber("orders")
    async def handle(_o: MsgOrder) -> None:
        pass

    spec = build_spec(memory_broker_json)
    schemas = spec["components"]["schemas"]
    assert "MsgOrder" in schemas
    assert "Address" in schemas
    payload = spec["components"]["messages"]["orders_payload"]["payload"]
    assert payload == {"$ref": "#/components/schemas/MsgOrder"}
    assert schemas["MsgOrder"]["properties"]["address"]["$ref"] == "#/components/schemas/Address"


@pytest.mark.skipif(not _is_installed("attrs"), reason="attrs not installed")
def test_attrs_validator_emits_schema(memory_broker_json: MemoryBroker) -> None:
    import attrs

    @attrs.define
    class AttrAddress:
        city: str

    @attrs.define
    class AttrOrder:
        id: int
        address: AttrAddress

    @memory_broker_json.subscriber("orders")
    async def handle(_o: AttrOrder) -> None:
        pass

    spec = build_spec(memory_broker_json)
    schemas = spec["components"]["schemas"]
    assert schemas["AttrOrder"]["properties"]["id"] == {"type": "integer"}
    assert schemas["AttrOrder"]["required"] == ["id", "address"]


def test_dataclass_validator_schema_lands_in_components(
    memory_broker_json: MemoryBroker,
) -> None:
    """The stdlib dataclass walker stays inline (no `$defs`); the hoist step puts the
    flat result under `components.schemas[type_name]` unchanged."""

    @memory_broker_json.subscriber("orders")
    async def handle(_o: Order) -> None:
        pass

    spec = build_spec(memory_broker_json)
    assert spec["components"]["schemas"]["Order"]["title"] == "Order"


@pytest.mark.skipif(not _is_installed("pydantic"), reason="pydantic not installed")
def test_shared_nested_schema_deduped_across_topics(
    memory_broker_json: MemoryBroker,
) -> None:
    from pydantic import BaseModel

    class Shared(BaseModel):
        x: int

    class Wrapper1(BaseModel):
        s: Shared

    class Wrapper2(BaseModel):
        s: Shared

    @memory_broker_json.subscriber("a")
    async def handle_a(_w: Wrapper1) -> None:
        pass

    @memory_broker_json.subscriber("b")
    async def handle_b(_w: Wrapper2) -> None:
        pass

    spec = build_spec(memory_broker_json)
    schemas = spec["components"]["schemas"]
    assert {"Wrapper1", "Wrapper2", "Shared"} <= set(schemas.keys())
    assert sum(1 for k in schemas if k == "Shared") == 1
