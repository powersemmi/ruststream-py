"""DI adapter for FastAPI's `Depends(...)` markers."""

import inspect
import typing
from typing import Annotated, Any, ClassVar

from ruststream.context import ContextRepo
from ruststream.di._base import DI, DIError
from ruststream.fastapi._errors import MissingDependencyError

try:
    import fastapi as _fastapi
except ImportError as exc:
    raise MissingDependencyError() from exc


_FASTAPI_DEPENDS = _fastapi.params.Depends


def Context() -> ContextRepo:  # noqa: N802
    """Sentinel marker: `Depends(Context)` injects the broker's `ContextRepo`.

    Calling `Context()` directly is a programmer error and raises immediately.
    """
    raise RuntimeError(
        "`Context` is a FastAPIDI sentinel, not a callable. "
        "Use it as `Depends(Context)` in a handler signature.",
    )


def _find_marker(annotation: Any, default: Any) -> Any:
    """Locate a `fastapi.Depends` marker on a parameter.

    Both `param=Depends(callable)` (default form) and
    `param: Annotated[T, Depends(callable)]` (annotation metadata) are supported.
    """
    if isinstance(default, _FASTAPI_DEPENDS):
        return default
    if typing.get_origin(annotation) is Annotated:
        for meta in typing.get_args(annotation)[1:]:
            if isinstance(meta, _FASTAPI_DEPENDS):
                return meta
    return None


async def _resolve_depender(
    depender: Any,
    context: ContextRepo,
    cache: dict[int, Any],
    use_cache: bool,
) -> Any:
    """Walk `depender`'s signature, resolve any nested `Depends(...)` recursively.

    `cache` is shared for the lifetime of one outer DI.resolve call so that two
    parameters of the same `depender` reusing the same sub-dependency see the
    same result (mirrors FastAPI's `use_cache=True` default). Entries are keyed
    by `id(callable)` because callables are not always hashable.
    """
    if depender is Context:
        return context
    cache_key = id(depender)
    if use_cache and cache_key in cache:
        return cache[cache_key]

    try:
        sig = inspect.signature(depender)
    except (TypeError, ValueError):
        sig = None

    kwargs: dict[str, Any] = {}
    if sig is not None:
        try:
            hints = typing.get_type_hints(depender, include_extras=True)
        except Exception:
            hints = {}
        for name, param in sig.parameters.items():
            annotation = hints.get(name, param.annotation)
            marker = _find_marker(annotation, param.default)
            if marker is None:
                if param.default is inspect.Parameter.empty:
                    raise DIError(
                        f"FastAPIDI cannot resolve parameter {name!r} of "
                        f"{getattr(depender, '__qualname__', depender)!r}: "
                        "no `Depends(...)` marker and no default value",
                    )
                continue
            kwargs[name] = await _resolve_depender(
                marker.dependency,
                context,
                cache,
                getattr(marker, "use_cache", True),
            )

    result = depender(**kwargs)
    if inspect.isawaitable(result):
        result = await result
    if use_cache:
        cache[cache_key] = result
    return result


class FastAPIDI(DI):
    """DI adapter recognising `fastapi.Depends(callable)` markers.

    Supported parameter shapes:
        * `param=Depends(callable)` -- FastAPI default form.
        * `param: Annotated[T, Depends(callable)]` -- FastAPI Annotated form.
        * `param=Depends(Context)` -- injects the broker's `ContextRepo`
          (`Context` is `ruststream.fastapi.Context`).

    Nested `Depends(...)` inside the callable's own signature are resolved
    recursively. Each `DI.resolve` call uses an independent cache that follows
    FastAPI's `use_cache=True` default: sub-dependencies shared between params
    of a single depender resolve once. The adapter holds no external resources,
    so `aclose()` is a no-op.
    """

    name: ClassVar[str] = "fastapi"

    def supports(self, annotation: Any, default: Any) -> bool:
        return _find_marker(annotation, default) is not None

    async def resolve(
        self,
        annotation: Any,
        *,
        context: ContextRepo,
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        marker = _find_marker(annotation, default)
        if marker is None:
            raise DIError(
                f"FastAPIDI cannot resolve {annotation!r}: parameter must use a "
                "`Depends(...)` marker (use `Depends(Context)` for `ContextRepo`)",
            )
        cache: dict[int, Any] = {}
        return await _resolve_depender(
            marker.dependency,
            context,
            cache,
            getattr(marker, "use_cache", True),
        )

    async def aclose(self) -> None:
        return None


def build() -> DI:
    """Construct and return a `FastAPIDI`."""
    return FastAPIDI()


__all__: tuple[str, ...] = ("Context", "FastAPIDI", "build")
