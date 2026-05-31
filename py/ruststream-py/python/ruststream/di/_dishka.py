"""Dishka adapter. Requires `pip install ruststream[dishka]`."""

import inspect
import typing
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from ruststream.context import ContextRepo
from ruststream.di._base import DI, DIError, MissingDependencyError

if TYPE_CHECKING:
    from dishka import AsyncContainer


_FROM_COMPONENT_TYPENAME = "_FromComponent"


def _is_from_dishka_marker(annotation: Any) -> bool:
    """Return True for `FromDishka[T]` (i.e. `Annotated[T, _FromComponent(...)]`)."""
    if typing.get_origin(annotation) is not Annotated:
        return False
    metadata = typing.get_args(annotation)[1:]
    return any(type(m).__name__ == _FROM_COMPONENT_TYPENAME for m in metadata)


def _unwrap_target(annotation: Any) -> Any:
    """Strip the `Annotated[...]` wrapper, returning the inner concrete type."""
    return typing.get_args(annotation)[0]


class DishkaDI(DI):
    """DI adapter backed by a Dishka `AsyncContainer`.

    Resolves parameters marked with `FromDishka[T]` (i.e. `Annotated[T, FromDishka]`):

        - `FromDishka[ContextRepo]`: returns the broker's shared `ContextRepo`. This
          is the *only* way to receive the broker context under DishkaDI; the bare
          `ContextRepo` annotation (which works under `NoOpDI`) raises at start time,
          keeping all DI-managed parameters routed through Dishka's marker syntax.
        - `FromDishka[T]` for any other `T`: returns the value Dishka builds for `T`
          from the supplied container.

    The container is consumed as-is: providers must live in the `Scope.APP` (or any
    scope already entered on `container`) for `container.get(T)` to succeed. If your
    providers require `Scope.REQUEST`, open the request container yourself and pass
    that as `container`, or wire a custom adapter that manages per-message scope.

    Lifecycle: `aclose()` calls `container.close()` so the broker tears down the
    container together with itself.
    """

    name: ClassVar[str] = "dishka"

    def __init__(self, container: "AsyncContainer") -> None:
        try:
            import dishka  # noqa: F401
        except ImportError as exc:
            raise MissingDependencyError("dishka", "dishka", "dishka") from exc
        self._container = container

    def supports(self, annotation: Any, default: Any) -> bool:
        del default
        return _is_from_dishka_marker(annotation)

    async def resolve(
        self,
        annotation: Any,
        *,
        context: ContextRepo,
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        del default
        if not _is_from_dishka_marker(annotation):
            raise DIError(
                f"DishkaDI cannot resolve {annotation!r}: wrap the type in "
                "`FromDishka[...]` to opt the parameter into Dishka resolution",
            )
        target = _unwrap_target(annotation)
        if target is ContextRepo:
            return context
        return await self._container.get(target)

    async def aclose(self) -> None:
        await self._container.close()


def build(container: "AsyncContainer") -> DI:
    """Construct and return a `DishkaDI` bound to `container`."""
    return DishkaDI(container)


__all__: tuple[str, ...] = ("DishkaDI", "build")
