"""AsyncAPI module errors."""


class AsyncAPIError(Exception):
    """Base error for `ruststream.asyncapi`."""


class MissingDependencyError(AsyncAPIError):
    """Raised when an optional AsyncAPI dependency (e.g. PyYAML) is missing."""

    def __init__(self, package: str, extra: str) -> None:
        super().__init__(
            f"feature requires the {package!r} package "
            f"(install via `pip install ruststream[{extra}]`)",
        )
        self.package = package
        self.extra = extra


__all__: tuple[str, ...] = ("AsyncAPIError", "MissingDependencyError")
