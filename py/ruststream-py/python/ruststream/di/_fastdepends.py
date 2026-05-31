"""FastDepends adapter. Requires `pip install ruststream[fast-depends]`."""

import inspect
import typing
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from ruststream.context import ContextRepo
from ruststream.di._base import DI, DIError, MissingDependencyError

if TYPE_CHECKING:
    from fast_depends.dependencies.model import Dependant


def Context() -> ContextRepo:  # noqa: N802
    """Sentinel marker: `Depends(Context)` injects the broker's `ContextRepo`.

    `FastDependsDI` intercepts a `Depends(Context)` marker before fast-depends would
    invoke it, so the function body is never executed at delivery time. Calling
    `Context()` directly is a programmer error and raises immediately to surface
    misuse.
    """
    raise RuntimeError(
        "`Context` is a FastDependsDI sentinel, not a callable. "
        "Use it as `Depends(Context)` in a handler signature.",
    )


def _find_dependant(annotation: Any, default: Any) -> "Dependant | None":
    """Locate a fast-depends `Dependant` marker on a parameter.

    Two equivalent ways to mark a parameter under fast-depends:
        * `param=Depends(callable)` -- the marker lives in the parameter's default.
        * `param: Annotated[T, Depends(callable)]` -- the marker lives in the
          annotation's `Annotated[...]` metadata.

    Both forms produce a `Dependant` instance; this helper returns the first one
    found, or `None` if the parameter is neither. Class-name matching keeps the
    check cheap and avoids importing `fast_depends` when the adapter is not in use.
    """
    marker: Any
    if (
        default is not inspect.Parameter.empty
        and default is not None
        and type(default).__name__ == "Dependant"
    ):
        marker = default
        return marker  # type: ignore[no-any-return]
    if typing.get_origin(annotation) is Annotated:
        for meta in typing.get_args(annotation)[1:]:
            if type(meta).__name__ == "Dependant":
                marker = meta
                return marker  # type: ignore[no-any-return]
    return None


class FastDependsDI(DI):
    """DI adapter that resolves parameters whose default is a `Depends(...)` marker.

    Supported parameter shape:
        - `param=Depends(callable)`: invokes `callable` and feeds the result. Nested
          `Depends(...)` inside `callable`'s signature are resolved by wrapping it
          with `fast_depends.inject` on first use, so the full fast-depends graph
          (sync + async dependencies, casting, caching) participates.
        - `param=Depends(Context)` (where `Context` is `ruststream.di.Context`):
          injects the broker's shared `ContextRepo`. Bare `ContextRepo` annotation
          (the `NoOpDI` convenience) is not supported under FastDependsDI, keeping
          every DI-managed parameter routed through fast-depends marker syntax.

    The adapter is stateless beyond a per-instance cache of wrapped dependers; it
    holds no external resources, so `aclose()` clears the cache.
    """

    name: ClassVar[str] = "fast_depends"

    def __init__(self) -> None:
        try:
            import fast_depends
        except ImportError as exc:
            raise MissingDependencyError(
                "fast_depends",
                "fast_depends",
                "fast-depends",
            ) from exc
        self._inject = fast_depends.inject
        self._injected_cache: dict[Any, Any] = {}

    def supports(self, annotation: Any, default: Any) -> bool:
        return _find_dependant(annotation, default) is not None

    async def resolve(
        self,
        annotation: Any,
        *,
        context: ContextRepo,
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        marker = _find_dependant(annotation, default)
        if marker is None:
            raise DIError(
                f"FastDependsDI cannot resolve {annotation!r}: parameter must default "
                "to `Depends(...)` or be annotated as `Annotated[T, Depends(...)]` "
                "(use `Depends(Context)` for `ContextRepo`)",
            )
        depender = marker.dependency
        if depender is Context:
            return context
        wrapped = self._injected_cache.get(depender)
        if wrapped is None:
            wrapped = self._inject(depender)
            self._injected_cache[depender] = wrapped
        result = wrapped()
        if inspect.isawaitable(result):
            return await result
        return result

    async def aclose(self) -> None:
        self._injected_cache.clear()


def build() -> DI:
    """Construct and return a `FastDependsDI`."""
    return FastDependsDI()


__all__: tuple[str, ...] = ("Context", "FastDependsDI", "build")
