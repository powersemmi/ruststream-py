"""`ruststream` command-line entry point.

The CLI itself ships behind the `ruststream[cli]` extra (which pulls in `click`).
This module is intentionally lightweight: importing `ruststream.cli` succeeds even
when `click` is absent, and only the call to :func:`main` triggers the dispatcher
to be loaded. That keeps the dependency truly optional -- a user who never invokes
the CLI does not pay for the extra import.

Three subcommands wrap the most common service-author chores:

    * `ruststream run <module:attr>` -- import the application object and drive its
      lifecycle (`asyncio.run(app.run())`). Works for both a `RustStream` app and a
      bare `Broker` (the latter is wrapped in a transient `RustStream` instance).
    * `ruststream asyncapi gen <module:attr>` -- import the broker / app, build an
      AsyncAPI 3.0 spec and print or write it (JSON by default; `--format yaml`
      requires the `ruststream[asyncapi]` extra).
    * `ruststream new <project>` -- scaffold a minimal in-memory service.
"""

from collections.abc import Sequence


class CLIMissingDependencyError(RuntimeError):
    """`click` is not installed; the CLI extra was not selected."""

    def __init__(self) -> None:
        super().__init__(
            "the `ruststream` CLI requires the `click` package "
            "(install via `pip install ruststream[cli]`)",
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Programmatic entry point used by the `ruststream` console-script.

    Lazily imports the click-based dispatcher so users without the `[cli]` extra
    can still import `ruststream` without pulling click. Returns the process
    exit code.
    """
    try:
        from ruststream.cli._main import main as _main
    except ImportError as exc:
        if exc.name == "click" or "click" in str(exc):
            raise CLIMissingDependencyError() from exc
        raise
    return _main(argv)


__all__: tuple[str, ...] = ("CLIMissingDependencyError", "main")
