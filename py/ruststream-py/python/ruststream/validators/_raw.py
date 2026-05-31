"""Identity validator for `bytes` / `bytearray` / `memoryview` payloads."""

from typing import Any, ClassVar

from ruststream.validators._base import Validator, ValidatorError


class RawBytesValidator(Validator):
    """Pass-through validator that hands raw payloads to handlers unchanged.

    Supports the concrete `bytes`, `bytearray`, and `memoryview` types. Useful when the
    handler wants the wire payload verbatim, ahead of any codec/validator chain.
    """

    name: ClassVar[str] = "raw"

    def supports(self, target_type: type) -> bool:
        return target_type in (bytes, bytearray, memoryview)

    def decode(self, data: Any, target_type: type) -> Any:
        if isinstance(data, (bytes, bytearray, memoryview)):
            return target_type(data) if target_type is not type(data) else data
        type_name = type(data).__name__
        raise ValidatorError(
            f"RawBytesValidator.decode expects bytes-like input, got {type_name}",
        )

    def encode(self, value: Any) -> Any:
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        type_name = type(value).__name__
        raise ValidatorError(
            f"RawBytesValidator.encode expects bytes-like input, got {type_name}",
        )

    def json_schema(self, target_type: type) -> dict[str, Any] | None:
        del target_type
        return None


__all__: tuple[str, ...] = ("RawBytesValidator",)
