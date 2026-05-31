"""Click-driven CLI dispatcher backing the `ruststream` console-script."""

import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

import click

from ruststream._broker import Broker
from ruststream.app import RustStream
from ruststream.asyncapi import build_spec, to_json, to_yaml
from ruststream.cli._loader import CLIError, load_target
from ruststream.cli._scaffold import scaffold


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="ruststream", prog_name="ruststream")
def cli() -> None:
    """RustStream service tooling: run apps, export AsyncAPI specs, scaffold projects."""


@cli.command(name="run")
@click.argument("target")
def run_cmd(target: str) -> None:
    """Drive the lifecycle of the application/broker at TARGET (`module:attr`)."""
    obj = _load_or_die(target)
    if isinstance(obj, Broker):
        asyncio.run(_run_broker(obj))
        return
    if isinstance(obj, RustStream):
        asyncio.run(obj.run())
        return
    raise click.ClickException(
        f"target {target!r} resolved to {type(obj).__name__}, expected a `RustStream` or `Broker`",
    )


async def _run_broker(broker: Broker) -> None:
    async with RustStream(broker):
        await asyncio.Event().wait()


@cli.group(name="asyncapi")
def asyncapi_group() -> None:
    """AsyncAPI 3.0 utilities (spec generation, viewer rendering)."""


@asyncapi_group.command(name="gen")
@click.argument("target")
@click.option("--title", default="RustStream service", show_default=True)
@click.option("--version", "version_", default="0.0.1", show_default=True)
@click.option("--description", default=None)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "yaml"], case_sensitive=False),
    default="json",
    show_default=True,
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="Write to PATH instead of stdout.",
)
def asyncapi_gen_cmd(
    target: str,
    title: str,
    version_: str,
    description: str | None,
    fmt: str,
    output: str | None,
) -> None:
    """Build an AsyncAPI 3.0 spec from TARGET (`module:attr`)."""
    obj = _load_or_die(target)
    if not isinstance(obj, Broker | RustStream):
        raise click.ClickException(
            f"target {target!r} resolved to {type(obj).__name__}, "
            "expected a `RustStream` or `Broker`",
        )
    spec = build_spec(obj, title=title, version=version_, description=description)
    text = to_yaml(spec) if fmt.lower() == "yaml" else to_json(spec)
    if output is None:
        click.echo(text, nl=fmt.lower() != "yaml")
    else:
        Path(output).write_text(text, encoding="utf-8")
        click.echo(f"wrote {output}", err=True)


@cli.command(name="new")
@click.argument("project")
@click.option(
    "--directory",
    "-d",
    type=click.Path(file_okay=False),
    default=".",
    show_default=True,
    help="Parent directory under which the project is created.",
)
def new_cmd(project: str, directory: str) -> None:
    """Scaffold a starter RustStream service named PROJECT."""
    try:
        files = scaffold(project, directory=Path(directory))
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("created:")
    for path in files:
        click.echo(f"  {path}")


def _load_or_die(target: str) -> object:
    try:
        return load_target(target)
    except CLIError as exc:
        raise click.ClickException(str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    """Programmatic entry point. Returns the process exit code."""
    try:
        cli.main(args=list(argv) if argv is not None else None, standalone_mode=False)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 0
    return 0


if __name__ == "__main__":  # pragma: no cover -- direct module execution
    sys.exit(main())


__all__: tuple[str, ...] = ("main",)
