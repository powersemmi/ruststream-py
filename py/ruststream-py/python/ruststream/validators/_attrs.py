"""attrs validator. Requires `pip install ruststream[attrs]`."""

from collections.abc import Mapping
from typing import Any, ClassVar, get_type_hints

from ruststream.validators._base import MissingDependencyError, Validator, ValidatorError


class AttrsValidator(Validator):
    """Validator for `attrs`-decorated classes.

    Decodes from a mapping by calling `target_type(**data)`; encodes via `attrs.asdict`.
    `json_schema` walks `attrs.fields(T)` and emits a minimal JSON Schema derived from
    Python annotations: primitive types map to their JSON Schema equivalents; nested
    attrs classes are inlined recursively. For richer schemas (constraints, formats,
    discriminators) plug in `apischema` or `cattrs` downstream.
    """

    name: ClassVar[str] = "attrs"

    def __init__(self) -> None:
        try:
            import attrs
        except ImportError as exc:
            raise MissingDependencyError("attrs", "attrs", "attrs") from exc
        self._attrs = attrs

    def supports(self, target_type: type) -> bool:
        return isinstance(target_type, type) and self._attrs.has(target_type)

    def decode(self, data: Any, target_type: type) -> Any:
        if not isinstance(data, Mapping):
            type_name = type(data).__name__
            raise ValidatorError(
                f"AttrsValidator.decode expects a mapping, got {type_name}",
            )
        try:
            return target_type(**data)
        except TypeError as exc:
            raise ValidatorError(
                f"AttrsValidator.decode failed to instantiate {target_type.__name__}: {exc}",
            ) from exc

    def encode(self, value: Any) -> Any:
        if not self._attrs.has(type(value)):
            type_name = type(value).__name__
            raise ValidatorError(
                f"AttrsValidator.encode expects an attrs instance, got {type_name}",
            )
        return self._attrs.asdict(value)

    def json_schema(self, target_type: type) -> dict[str, Any] | None:
        if not self.supports(target_type):
            return None
        hints = get_type_hints(target_type)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in self._attrs.fields(target_type):
            properties[field.name] = _annotation_to_schema(
                hints.get(field.name, field.type),
                self,
            )
            if field.default is self._attrs.NOTHING:
                required.append(field.name)
        schema: dict[str, Any] = {
            "type": "object",
            "title": target_type.__name__,
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema


_PRIMITIVE_SCHEMA: dict[type, dict[str, str]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    bytes: {"type": "string", "format": "binary"},
}


def _annotation_to_schema(annotation: Any, validator: "AttrsValidator") -> dict[str, Any]:
    if isinstance(annotation, type):
        if annotation in _PRIMITIVE_SCHEMA:
            return dict(_PRIMITIVE_SCHEMA[annotation])
        if validator._attrs.has(annotation):
            nested = validator.json_schema(annotation)
            if nested is not None:
                return nested
    return {}


def build() -> Validator:
    """Construct and return an `AttrsValidator`."""
    return AttrsValidator()


__all__: tuple[str, ...] = ("AttrsValidator", "build")
