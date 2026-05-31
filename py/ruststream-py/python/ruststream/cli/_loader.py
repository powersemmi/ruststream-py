"""Import the application target from a `module:attr` reference."""

import importlib
import sys
from pathlib import Path
from typing import Any


class CLIError(Exception):
    """Raised when a CLI command cannot proceed (missing target, bad path, etc.)."""


def _ensure_cwd_on_path() -> None:
    """Make the current working directory importable so `myapp:broker` resolves."""
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)


def load_target(reference: str) -> Any:
    """Resolve `module:attr` (or `module:attr.subattr`) into an imported object.

    Raises :class:`CLIError` with a human-readable message when the reference is
    malformed or when the import fails.
    """
    if ":" not in reference:
        raise CLIError(
            f"target {reference!r} must be in `module[.sub]:attr[.subattr]` form",
        )
    module_path, _, attr_path = reference.partition(":")
    if not module_path or not attr_path:
        raise CLIError(
            f"target {reference!r} must include both module and attribute parts",
        )
    _ensure_cwd_on_path()
    try:
        obj: Any = importlib.import_module(module_path)
    except ImportError as exc:
        raise CLIError(f"cannot import module {module_path!r}: {exc}") from exc
    for part in attr_path.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError as exc:
            raise CLIError(
                f"module {module_path!r} has no attribute path {attr_path!r}: {exc}",
            ) from exc
    return obj


__all__: tuple[str, ...] = ("CLIError", "load_target")
