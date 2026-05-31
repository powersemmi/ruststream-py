"""Validator protocol + shared errors."""

from typing import Any, ClassVar, Protocol, runtime_checkable


class ValidatorError(Exception):
    """Raised when a validator fails to decode or encode a value."""


class MissingDependencyError(ValidatorError):
    """A validator adapter is unavailable because its backing PyPI package is not installed.

    The message includes the exact `pip install` hint the user should run.
    """

    def __init__(self, validator_name: str, package: str, extra: str) -> None:
        super().__init__(
            f"validator {validator_name!r} requires the {package!r} package "
            f"(install via `pip install ruststream[{extra}]`)",
        )
        self.validator_name = validator_name
        self.package = package
        self.extra = extra


@runtime_checkable
class Validator(Protocol):
    """Schema-aware validator used to materialize handler parameters from decoded payloads.

    A validator owns one part of the type domain (Pydantic owns `BaseModel` subclasses,
    msgspec owns `Struct`, dataclasses owns `@dataclass`, the raw-bytes validator owns
    `bytes`). The registry dispatches a target type to the first validator whose
    `supports()` returns `True`.
    """

    name: ClassVar[str]

    def supports(self, target_type: type) -> bool:
        """Return `True` when this validator can handle `target_type`."""
        ...

    def decode(self, data: Any, target_type: type) -> Any:
        """Build a `target_type` instance from `data` (typically a `dict` from a codec)."""
        ...

    def encode(self, value: Any) -> Any:
        """Convert a validated value into a primitive shape (`dict`, `list`, scalar) that
        a `Codec` can serialize."""
        ...

    def json_schema(self, target_type: type) -> dict[str, Any] | None:
        """JSON Schema for `target_type`, used by AsyncAPI generation. Return `None` when
        the validator does not produce schemas (e.g. raw bytes)."""
        ...


__all__: tuple[str, ...] = ("MissingDependencyError", "Validator", "ValidatorError")
