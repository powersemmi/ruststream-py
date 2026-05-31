"""Translate broker / router metadata into an AsyncAPI 3.0 document."""

import re
from typing import Any

from ruststream._broker import Broker, Router, _payload_type_of
from ruststream.app import RustStream
from ruststream.asyncapi._schema import hoist_schema
from ruststream.codecs import Codec, resolve_codec
from ruststream.validators import resolve_validator

ASYNCAPI_VERSION = "3.0.0"

_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")


def _slugify(text: str) -> str:
    """Convert a topic name into an AsyncAPI-safe identifier."""
    slug = _SLUG_RE.sub("_", text).strip("_")
    return slug or "channel"


def _type_id(target_type: type) -> str:
    """Stable identifier for a schema in `components/schemas/...`."""
    return getattr(target_type, "__name__", repr(target_type))


def _operation_id(action: str, topic: str) -> str:
    return f"{action}_{_slugify(topic)}"


def _empty_components() -> dict[str, dict[str, Any]]:
    return {"messages": {}, "schemas": {}}


def _payload_schema_ref(
    target_type: type | None,
    components_schemas: dict[str, dict[str, Any]],
) -> str | None:
    """Resolve `target_type` through the validator registry and hoist its schema.

    Returns the key inside `components_schemas` (idempotent across calls), or
    `None` when no validator claims the type or none produces a JSON Schema.
    """
    if target_type is None:
        return None
    validator = resolve_validator(target_type)
    if validator is None:
        return None
    schema = validator.json_schema(target_type)
    if schema is None:
        return None
    return hoist_schema(
        schema,
        type_name=_type_id(target_type),
        components_schemas=components_schemas,
    )


def _add_channel(
    channels: dict[str, Any],
    messages: dict[str, Any],
    schemas: dict[str, Any],
    topic: str,
    target_type: type | None,
    *,
    content_type: str | None,
) -> tuple[str, str]:
    """Register `topic` as a channel (idempotent) and attach a message reference.

    Returns `(channel_id, message_id)` for use when wiring operations.
    """
    channel_id = _slugify(topic)
    message_id = f"{channel_id}_payload"
    channel = channels.setdefault(channel_id, {"address": topic, "messages": {}})

    schema_id = _payload_schema_ref(target_type, schemas)
    message_entry: dict[str, Any] = messages.setdefault(message_id, {"name": message_id})
    if schema_id is not None:
        message_entry["payload"] = {"$ref": f"#/components/schemas/{schema_id}"}
    if content_type is not None:
        message_entry["contentType"] = content_type
    channel["messages"][message_id] = {"$ref": f"#/components/messages/{message_id}"}
    return channel_id, message_id


def _resolve_codec_content_type(
    codec_ref: Codec | str | None,
    fallback: Codec | None,
) -> str | None:
    """Return the `content_type` attribute for the codec attached to `reg`."""
    try:
        codec = resolve_codec(codec_ref, fallback=fallback)
    except Exception:
        return None
    return getattr(codec, "content_type", None)


def _build_from_registrations(
    registrations: list[Any],
    *,
    default_codec: Codec | None,
    title: str,
    version: str,
    description: str | None,
) -> dict[str, Any]:
    channels: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    components = _empty_components()
    messages, schemas = components["messages"], components["schemas"]

    for reg in registrations:
        payload_type = _payload_type_of(reg.handler)
        sub_content_type = _resolve_codec_content_type(reg.codec, default_codec)
        channel_id, message_id = _add_channel(
            channels,
            messages,
            schemas,
            reg.topic,
            payload_type,
            content_type=sub_content_type,
        )
        op_id = _operation_id("receive", reg.topic)
        operations[op_id] = {
            "action": "receive",
            "channel": {"$ref": f"#/channels/{channel_id}"},
            "messages": [{"$ref": f"#/channels/{channel_id}/messages/{message_id}"}],
        }
        for target in reg.publish_to:
            pub_content_type = _resolve_codec_content_type(target.codec, default_codec)
            pub_channel_id, pub_message_id = _add_channel(
                channels,
                messages,
                schemas,
                target.topic,
                target_type=None,
                content_type=pub_content_type,
            )
            send_id = _operation_id("send", target.topic)
            operations[send_id] = {
                "action": "send",
                "channel": {"$ref": f"#/channels/{pub_channel_id}"},
                "messages": [
                    {"$ref": f"#/channels/{pub_channel_id}/messages/{pub_message_id}"},
                ],
            }

    info: dict[str, Any] = {"title": title, "version": version}
    if description is not None:
        info["description"] = description
    return {
        "asyncapi": ASYNCAPI_VERSION,
        "info": info,
        "channels": channels,
        "operations": operations,
        "components": components,
    }


def _build_from_broker(
    broker: Broker,
    *,
    title: str,
    version: str,
    description: str | None,
) -> dict[str, Any]:
    return _build_from_registrations(
        list(broker.registrations),
        default_codec=getattr(broker, "_default_codec", None),
        title=title,
        version=version,
        description=description,
    )


def build_spec(
    target: Broker | RustStream,
    *,
    title: str = "RustStream service",
    version: str = "0.0.1",
    description: str | None = None,
) -> dict[str, Any]:
    """Build an AsyncAPI 3.0 spec dict for `target`.

    Accepts either a single :class:`Broker` or the top-level :class:`RustStream` (every
    registered broker contributes its channels/operations to the merged spec).

    Schemas produced by Pydantic / msgspec validators are normalized: their `$defs`
    table is hoisted into `components.schemas` and every `#/$defs/...` reference is
    rewritten to `#/components/schemas/...`. Messages also carry a `contentType`
    derived from the subscriber's codec (broker default or per-registration override).
    """
    if isinstance(target, RustStream):
        merged: dict[str, Any] | None = None
        for broker in target.brokers:
            partial = _build_from_broker(
                broker, title=title, version=version, description=description
            )
            if merged is None:
                merged = partial
                continue
            for key in ("channels", "operations"):
                merged[key].update(partial[key])
            for inner_key in ("messages", "schemas"):
                merged["components"][inner_key].update(partial["components"][inner_key])
        if merged is None:
            info: dict[str, Any] = {"title": title, "version": version}
            if description is not None:
                info["description"] = description
            return {
                "asyncapi": ASYNCAPI_VERSION,
                "info": info,
                "channels": {},
                "operations": {},
                "components": _empty_components(),
            }
        return merged
    return _build_from_broker(target, title=title, version=version, description=description)


def build_spec_for_router(
    router: Router,
    *,
    title: str = "RustStream router",
    version: str = "0.0.1",
    description: str | None = None,
) -> dict[str, Any]:
    """Build an AsyncAPI spec from a standalone :class:`Router` (no broker attached).

    Routers have no broker-level default codec, so `contentType` is filled only when a
    subscriber / publisher pins its own codec via the decorator's `codec=` kwarg.
    """
    return _build_from_registrations(
        list(router.registrations),
        default_codec=None,
        title=title,
        version=version,
        description=description,
    )


__all__: tuple[str, ...] = ("ASYNCAPI_VERSION", "build_spec", "build_spec_for_router")
