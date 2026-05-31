"""Pluggable dependency injection providers for handler signatures.

`DI` resolves handler parameters that follow the validated payload. Brokers attach one
`DI` instance; subscribers can override per topic. The default `NoOpDI` resolves only the
broker's `ContextRepo`, keeping DI opt-in for any other type.

Ecosystem adapters live behind PyPI extras and are exposed lazily; importing them at
package level would force every install to carry the backing dependency.

    - `pip install ruststream[dishka]` enables `DishkaDI` for `FromDishka[T]` markers.
    - `pip install ruststream[fast-depends]` enables `FastDependsDI` for `Depends(...)`
      defaults.

Handler example with `NoOpDI` (the default):

    @broker.subscriber("orders")
    async def handle(order: Order, ctx: ContextRepo) -> None:
        ctx.set_global("last_order", order)
"""

from typing import TYPE_CHECKING, Any

from ruststream.di._base import DI, DIError, MissingDependencyError
from ruststream.di._noop import NoOpDI

if TYPE_CHECKING:
    from ruststream.di._dishka import DishkaDI
    from ruststream.di._fastdepends import Context, FastDependsDI


_LAZY_MODULES: dict[str, str] = {
    "DishkaDI": "ruststream.di._dishka",
    "FastDependsDI": "ruststream.di._fastdepends",
    "Context": "ruststream.di._fastdepends",
}


def __getattr__(name: str) -> Any:
    """Lazily import optional DI adapters on first attribute access."""
    module_path = _LAZY_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module 'ruststream.di' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    attr = getattr(module, name)
    globals()[name] = attr
    return attr


__all__: tuple[str, ...] = (
    "DI",
    "Context",
    "DIError",
    "DishkaDI",
    "FastDependsDI",
    "MissingDependencyError",
    "NoOpDI",
)
