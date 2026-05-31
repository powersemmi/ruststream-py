"""msgspec validator. Requires `pip install ruststream[msgspec]`."""

from typing import Any, ClassVar

from ruststream.validators._base import MissingDependencyError, Validator, ValidatorError


class MsgspecValidator(Validator):
    """Validator for `msgspec.Struct` subclasses.

    Uses `msgspec.convert` for decode and `msgspec.to_builtins` for encode. `json_schema`
    delegates to `msgspec.json.schema`.
    """

    name: ClassVar[str] = "msgspec"

    def __init__(self) -> None:
        try:
            import msgspec
        except ImportError as exc:
            raise MissingDependencyError("msgspec", "msgspec", "msgspec") from exc
        self._msgspec = msgspec

    def supports(self, target_type: type) -> bool:
        return isinstance(target_type, type) and issubclass(
            target_type,
            self._msgspec.Struct,
        )

    def decode(self, data: Any, target_type: type) -> Any:
        try:
            return self._msgspec.convert(data, type=target_type)
        except self._msgspec.ValidationError as exc:
            raise ValidatorError(
                f"msgspec validation failed for {target_type.__name__}: {exc}",
            ) from exc

    def encode(self, value: Any) -> Any:
        if not isinstance(value, self._msgspec.Struct):
            type_name = type(value).__name__
            raise ValidatorError(
                f"MsgspecValidator.encode expects a Struct instance, got {type_name}",
            )
        return self._msgspec.to_builtins(value)

    def json_schema(self, target_type: type) -> dict[str, Any] | None:
        if not self.supports(target_type):
            return None
        schema: dict[str, Any] = self._msgspec.json.schema(target_type)
        return schema


def build() -> Validator:
    """Construct and return a `MsgspecValidator`."""
    return MsgspecValidator()


__all__: tuple[str, ...] = ("MsgspecValidator", "build")
