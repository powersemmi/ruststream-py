"""FastAPI integration: DI adapter, lifespan helper, and route mounts.

Two scenarios this module covers:

    1. **Embed a RustStream broker inside a FastAPI app.** :func:`lifespan_for`
       returns a FastAPI-compatible lifespan callable that starts and stops a
       :class:`~ruststream.RustStream` (or a bare :class:`~ruststream.Broker`)
       alongside the HTTP server. Pair it with :func:`mount_asyncapi` to expose
       the broker's AsyncAPI 3.0 spec and viewer, and with :func:`mount_metrics`
       to expose Prometheus metrics, all from the same ASGI process.

    2. **Use FastAPI's `Depends(...)` markers inside broker handlers.**
       :class:`FastAPIDI` is the DI provider that recognises
       `fastapi.params.Depends` markers (both default and Annotated forms) and
       resolves nested dependencies recursively. :data:`Context` is the sentinel
       passed to `Depends(Context)` to receive the broker's `ContextRepo`.

Requires `pip install ruststream[fastapi]`. Importing `ruststream.fastapi`
itself is cheap; touching any of the public names triggers the import of the
inner module which raises :class:`MissingDependencyError` if `fastapi` is
absent.
"""

from typing import TYPE_CHECKING, Any

from ruststream.fastapi._errors import MissingDependencyError

if TYPE_CHECKING:
    from ruststream.fastapi._di import Context, FastAPIDI
    from ruststream.fastapi._lifespan import lifespan_for
    from ruststream.fastapi._mounts import mount_asyncapi, mount_metrics


_LAZY_MODULES: dict[str, str] = {
    "Context": "ruststream.fastapi._di",
    "FastAPIDI": "ruststream.fastapi._di",
    "lifespan_for": "ruststream.fastapi._lifespan",
    "mount_asyncapi": "ruststream.fastapi._mounts",
    "mount_metrics": "ruststream.fastapi._mounts",
}


def __getattr__(name: str) -> Any:
    module_path = _LAZY_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module 'ruststream.fastapi' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    attr = getattr(module, name)
    globals()[name] = attr
    return attr


__all__: tuple[str, ...] = (
    "Context",
    "FastAPIDI",
    "MissingDependencyError",
    "lifespan_for",
    "mount_asyncapi",
    "mount_metrics",
)
