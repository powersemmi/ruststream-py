"""DI protocol + shared errors."""

import inspect
from typing import Any, ClassVar, Protocol, runtime_checkable

from ruststream.context import ContextRepo


class DIError(Exception):
    """Raised when a DI provider cannot resolve a parameter."""


class MissingDependencyError(DIError):
    """A DI adapter is unavailable because its backing PyPI package is not installed.

    The message includes the exact `pip install` hint the user should run.
    """

    def __init__(self, provider_name: str, package: str, extra: str) -> None:
        super().__init__(
            f"DI provider {provider_name!r} requires the {package!r} package "
            f"(install via `pip install ruststream[{extra}]`)",
        )
        self.provider_name = provider_name
        self.package = package
        self.extra = extra


@runtime_checkable
class DI(Protocol):
    """Provider that materializes handler parameters after the payload.

    A `DI` decides whether it can produce a value for one handler parameter
    (`supports(annotation, default)`), then provides the value at delivery time
    (`resolve(annotation, *, context, default)`). It also owns its teardown step
    (`aclose`).

    The builtin `NoOpDI` resolves only `ContextRepo`; ecosystem adapters extend the
    supported domain (Dishka resolves `FromDishka[T]`, FastDepends resolves parameters
    whose default is a `Depends(...)` marker). Each `Broker` holds one `DI` instance;
    subscribers can override.

    `default` carries the parameter's declared default (or `inspect.Parameter.empty`).
    Adapters that pivot on default-encoded markers (FastDepends) need it; adapters
    that only inspect the annotation may ignore it.
    """

    name: ClassVar[str]

    def supports(self, annotation: Any, default: Any) -> bool:
        """Decide whether this provider can resolve a handler parameter.

        Args:
            annotation: Type annotation of the parameter (`inspect.Parameter.annotation`).
            default: Default value, or `inspect.Parameter.empty` when absent.
        """
        ...

    async def resolve(
        self,
        annotation: Any,
        *,
        context: ContextRepo,
        default: Any = inspect.Parameter.empty,
    ) -> Any:
        """Build the value for a parameter the provider claimed to support."""
        ...

    async def aclose(self) -> None:
        """Release any provider-owned resources. Called once on broker shutdown."""
        ...


__all__: tuple[str, ...] = ("DI", "DIError", "MissingDependencyError")
