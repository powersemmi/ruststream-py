"""Pluggable schema validators for RustStream.

A `Validator` materializes typed handler parameters from decoded payloads. Validators are
looked up by handler-parameter type through a registry of `supports(target_type)` checks.

Built-in validators (no extras required):
    - `RawBytesValidator`: passes `bytes` / `bytearray` / `memoryview` through unchanged.
    - `DataclassValidator`: handles `@dataclass` types using stdlib `dataclasses`.

Ecosystem adapters (install the matching extra):
    - `pydantic` (`pip install ruststream[pydantic]`): wraps Pydantic v2 `BaseModel`.
    - `msgspec` (`pip install ruststream[msgspec]`): wraps `msgspec.Struct`.
    - `attrs` (`pip install ruststream[attrs]`): wraps `attrs`/`attr.s` classes.

External validators register through the `ruststream.validators` entry-point group and
load on first lookup.
"""

from ruststream.validators._base import (
    MissingDependencyError,
    Validator,
    ValidatorError,
)
from ruststream.validators._dataclass import DataclassValidator
from ruststream.validators._raw import RawBytesValidator
from ruststream.validators._registry import (
    ValidatorRegistry,
    register_validator,
    resolve_validator,
)

__all__: tuple[str, ...] = (
    "DataclassValidator",
    "MissingDependencyError",
    "RawBytesValidator",
    "Validator",
    "ValidatorError",
    "ValidatorRegistry",
    "register_validator",
    "resolve_validator",
)
