"""Normalize validator-produced JSON Schemas for embedding into AsyncAPI components.

Pydantic and msgspec emit schemas that use a top-level `$defs` table and `$ref`
pointers of the form `#/$defs/Name`. AsyncAPI 3.0 expects every reusable schema
to live in `components.schemas` and references to look like
`#/components/schemas/Name`. :func:`hoist_schema` does that rewrite:

    1. Pop the schema's `$defs` table (if any) and place each entry in the supplied
       `components_schemas` dict (idempotently: pre-existing entries are kept, so
       cross-channel reuse of the same model produces a single schema record).
    2. Walk the remaining schema and rewrite any `$ref` value that starts with
       `#/$defs/` to the equivalent `#/components/schemas/` path.
    3. If the rewritten top-level reduces to a bare `$ref`, return the referenced
       component name (msgspec form). Otherwise register the schema itself under
       `type_name` and return that.

The returned key is the value AsyncAPI message authors should use to construct
`{"$ref": f"#/components/schemas/{key}"}`.
"""

from typing import Any

_DEFS_PREFIX = "#/$defs/"
_COMPONENTS_PREFIX = "#/components/schemas/"


def _rewrite_refs(node: Any) -> Any:
    """Return a deep copy of `node` with every `#/$defs/...` ref pointed at components."""
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith(_DEFS_PREFIX):
                result[key] = _COMPONENTS_PREFIX + value[len(_DEFS_PREFIX) :]
            else:
                result[key] = _rewrite_refs(value)
        return result
    if isinstance(node, list):
        return [_rewrite_refs(item) for item in node]
    return node


def hoist_schema(
    schema: dict[str, Any],
    *,
    type_name: str,
    components_schemas: dict[str, dict[str, Any]],
) -> str:
    """Hoist `schema['$defs']` into `components_schemas` and return the primary key.

    See module docstring for the algorithm. The input `schema` is not mutated.
    """
    working = dict(schema)
    defs = working.pop("$defs", {})
    if isinstance(defs, dict):
        for sub_name, sub_schema in defs.items():
            if sub_name in components_schemas:
                continue
            if isinstance(sub_schema, dict):
                components_schemas[sub_name] = _rewrite_refs(sub_schema)

    rewritten = _rewrite_refs(working)
    if (
        isinstance(rewritten, dict)
        and set(rewritten.keys()) == {"$ref"}
        and isinstance(rewritten["$ref"], str)
        and rewritten["$ref"].startswith(_COMPONENTS_PREFIX)
    ):
        return rewritten["$ref"][len(_COMPONENTS_PREFIX) :]

    if type_name not in components_schemas and isinstance(rewritten, dict):
        components_schemas[type_name] = rewritten
    return type_name


__all__: tuple[str, ...] = ("hoist_schema",)
