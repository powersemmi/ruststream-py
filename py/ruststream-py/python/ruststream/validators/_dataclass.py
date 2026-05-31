"""Validator for stdlib `dataclasses`."""

import dataclasses
from collections.abc import Mapping
from typing import Any, ClassVar, get_type_hints

from ruststream.validators._base import Validator, ValidatorError


class DataclassValidator(Validator):
    """Stdlib `dataclasses` validator.

    `supports(T)` returns `True` for any class decorated with `@dataclass`. `decode`
    constructs `T(**data)`; nested dataclass fields are converted recursively. `encode`
    returns the result of `dataclasses.asdict`. `json_schema` produces a minimal schema
    derived from type annotations.
    """

    name: ClassVar[str] = "dataclass"

    def supports(self, target_type: type) -> bool:
        return dataclasses.is_dataclass(target_type)

    def decode(self, data: Any, target_type: type) -> Any:
        if not isinstance(data, Mapping):
            type_name = type(data).__name__
            raise ValidatorError(
                f"DataclassValidator.decode expects a mapping, got {type_name}",
            )
        hints = get_type_hints(target_type)
        kwargs: dict[str, Any] = {}
        for field in dataclasses.fields(target_type):
            if field.name not in data:
                if (
                    field.default is dataclasses.MISSING
                    and field.default_factory is dataclasses.MISSING
                ):
                    raise ValidatorError(
                        f"missing required field {field.name!r} for {target_type.__name__}",
                    )
                continue
            raw_value = data[field.name]
            field_type = hints.get(field.name, field.type)
            kwargs[field.name] = self._decode_field(raw_value, field_type)
        try:
            return target_type(**kwargs)
        except TypeError as exc:
            raise ValidatorError(
                f"DataclassValidator.decode failed to instantiate {target_type.__name__}: {exc}",
            ) from exc

    def _decode_field(self, value: Any, field_type: Any) -> Any:
        if isinstance(field_type, type) and dataclasses.is_dataclass(field_type):
            return self.decode(value, field_type)
        return value

    def encode(self, value: Any) -> Any:
        if not dataclasses.is_dataclass(value) or isinstance(value, type):
            type_name = type(value).__name__
            raise ValidatorError(
                f"DataclassValidator.encode expects a dataclass instance, got {type_name}",
            )
        return dataclasses.asdict(value)

    def json_schema(self, target_type: type) -> dict[str, Any] | None:
        if not dataclasses.is_dataclass(target_type):
            return None
        hints = get_type_hints(target_type)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in dataclasses.fields(target_type):
            properties[field.name] = _annotation_to_schema(hints.get(field.name, field.type))
            if (
                field.default is dataclasses.MISSING
                and field.default_factory is dataclasses.MISSING
            ):
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


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    if isinstance(annotation, type):
        if annotation in _PRIMITIVE_SCHEMA:
            return dict(_PRIMITIVE_SCHEMA[annotation])
        if dataclasses.is_dataclass(annotation):
            nested = DataclassValidator().json_schema(annotation)
            if nested is not None:
                return nested
    return {}


__all__: tuple[str, ...] = ("DataclassValidator",)
