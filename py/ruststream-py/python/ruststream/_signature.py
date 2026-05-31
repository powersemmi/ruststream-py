"""Signature introspection helpers shared by broker dispatch and app lifecycle.

Both the broker handler chain and the app-level lifespan/hook runner translate user
callables into a list of `_Dependency` records that a `DI` provider can resolve. The
broker skips the first positional parameter (it is the validated payload); the app
treats every positional parameter as a DI dependency.
"""

import inspect
from collections.abc import Callable
from typing import Any, NamedTuple, get_type_hints


class _Dependency(NamedTuple):
    """One callable parameter that a `DI` provider will resolve at invocation time."""

    name: str
    annotation: Any
    default: Any


def _positional_params(callback: Callable[..., Any]) -> list[inspect.Parameter]:
    try:
        sig = inspect.signature(callback)
    except (TypeError, ValueError):
        return []
    return [
        p
        for p in sig.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]


def _resolved_hints(callback: Callable[..., Any]) -> dict[str, Any]:
    try:
        return get_type_hints(callback, include_extras=True)
    except Exception:
        return {}


def collect_dependencies(
    callback: Callable[..., Any],
    *,
    skip_first: bool,
) -> list[_Dependency]:
    """Return one `_Dependency` per positional parameter, optionally skipping the first.

    Set `skip_first=True` for broker handlers (the first positional is the payload, not a
    DI dependency); set `skip_first=False` for lifespan / lifecycle hooks where every
    positional parameter is DI-resolved.
    """
    positional = _positional_params(callback)
    start = 1 if skip_first else 0
    if len(positional) <= start:
        return []
    hints = _resolved_hints(callback)
    return [
        _Dependency(name=p.name, annotation=hints.get(p.name, p.annotation), default=p.default)
        for p in positional[start:]
    ]


__all__: tuple[str, ...] = ("_Dependency", "_positional_params", "collect_dependencies")
