"""Validator registry: ordered dispatch by `supports(target_type)`."""

import logging
from importlib.metadata import entry_points
from typing import Final

from ruststream.validators._base import Validator, ValidatorError
from ruststream.validators._dataclass import DataclassValidator
from ruststream.validators._raw import RawBytesValidator

logger = logging.getLogger(__name__)


class ValidatorRegistry:
    """Ordered chain of validators.

    `resolve(target_type)` returns the first registered validator whose `supports()` says
    yes. Insertion order matters: validators registered earlier win when their support
    ranges overlap. `RawBytesValidator` and `DataclassValidator` register on construction;
    ecosystem adapters load lazily via the `ruststream.validators` entry-point group.
    """

    _LAZY_BUILTINS: Final[dict[str, str]] = {
        "pydantic": "ruststream.validators._pydantic",
        "msgspec": "ruststream.validators._msgspec",
        "attrs": "ruststream.validators._attrs",
    }

    def __init__(self) -> None:
        self._validators: list[Validator] = []
        self._entry_points_loaded: bool = False
        self.register(RawBytesValidator())
        self.register(DataclassValidator())

    def register(self, validator: Validator) -> None:
        """Append `validator` to the chain."""
        self._validators.append(validator)

    def load_extra(self, name: str) -> Validator:
        """Force-load the ecosystem adapter `name` and return its registered instance."""
        if name not in self._LAZY_BUILTINS:
            raise ValidatorError(f"no lazy adapter registered under {name!r}")
        module_path = self._LAZY_BUILTINS[name]
        import importlib

        module = importlib.import_module(module_path)
        validator: Validator = module.build()
        self.register(validator)
        return validator

    def resolve(self, target_type: type) -> Validator | None:
        """Return the first validator whose `supports(target_type)` is True. Triggers
        lazy loading and entry-point loading on first call."""
        for validator in self._validators:
            if validator.supports(target_type):
                return validator
        for name in self._LAZY_BUILTINS:
            try:
                validator = self.load_extra(name)
            except Exception as exc:
                logger.debug("validator adapter %s unavailable: %s", name, exc)
                continue
            if validator.supports(target_type):
                return validator
        if not self._entry_points_loaded:
            self._load_entry_points()
            for validator in self._validators:
                if validator.supports(target_type):
                    return validator
        return None

    def _load_entry_points(self) -> None:
        self._entry_points_loaded = True
        try:
            eps = list(entry_points(group="ruststream.validators"))
        except TypeError:
            eps = []
        for ep in eps:
            try:
                factory = ep.load()
            except ImportError:
                logger.debug(
                    "ruststream.validators entry-point %s failed to import",
                    ep.name,
                )
                continue
            try:
                self.register(factory())
            except Exception:
                logger.exception(
                    "ruststream.validators entry-point %s factory raised",
                    ep.name,
                )


_global_registry = ValidatorRegistry()


def register_validator(validator: Validator) -> None:
    """Register `validator` in the process-global registry."""
    _global_registry.register(validator)


def resolve_validator(target_type: type) -> Validator | None:
    """Look up a validator for `target_type` in the process-global registry."""
    return _global_registry.resolve(target_type)


__all__: tuple[str, ...] = (
    "ValidatorRegistry",
    "register_validator",
    "resolve_validator",
)
