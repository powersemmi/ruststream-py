"""NoOp DI: resolves only `ContextRepo`. Default for brokers without an attached container."""

import inspect
from typing import Any, ClassVar

from ruststream.context import ContextRepo
from ruststream.di._base import DI, DIError


class NoOpDI(DI):
    """Minimal DI that hands out the shared `ContextRepo` and nothing else.

    Any handler parameter annotated as `ContextRepo` is resolved to the broker's
    context. Every other parameter type is rejected: callers either reach for a richer
    DI provider (`Dishka` / `FastDepends`) or keep the handler signature limited to
    payload and optional context.
    """

    name: ClassVar[str] = "noop"

    def supports(self, annotation: Any, default: Any) -> bool:
        del default
        return annotation is ContextRepo

    async def resolve(
        self,
        annotation: Any,
        *,
        context: ContextRepo,
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        del default
        if annotation is ContextRepo:
            return context
        raise DIError(
            f"NoOpDI cannot resolve {annotation!r}; configure a DI container "
            "(`broker = MemoryBroker(di=DishkaDI(container))`) to inject custom types",
        )

    async def aclose(self) -> None:
        return None


__all__: tuple[str, ...] = ("NoOpDI",)
