"""FastAPI integration errors."""


class MissingDependencyError(RuntimeError):
    """`fastapi` is not installed; install `ruststream[fastapi]` to enable the bridge."""

    def __init__(self) -> None:
        super().__init__(
            "ruststream.fastapi requires the 'fastapi' package "
            "(install via `pip install ruststream[fastapi]`)",
        )


__all__: tuple[str, ...] = ("MissingDependencyError",)
