"""`ruststream` console-script: loader resolution, asyncapi gen, scaffold."""

import importlib.util
import json
import sys
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner
from ruststream.cli._loader import CLIError, load_target
from ruststream.cli._main import cli
from ruststream.cli._scaffold import scaffold


def _has_yaml() -> bool:
    return importlib.util.find_spec("yaml") is not None


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def sample_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Write a tiny module on disk that exposes `broker` (a MemoryBroker)."""
    module_name = "_ruststream_cli_sample"
    source = textwrap.dedent(
        """
        from ruststream import MemoryBroker, Message

        broker = MemoryBroker(codec="json")

        @broker.subscriber("orders")
        async def handle(_msg: Message) -> None:
            pass
        """,
    )
    (tmp_path / f"{module_name}.py").write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    return module_name


def test_load_target_resolves_module_attr(sample_app: str) -> None:
    obj = load_target(f"{sample_app}:broker")
    assert obj is not None
    assert type(obj).__name__ == "MemoryBroker"


@pytest.mark.parametrize(
    "reference",
    [
        "no_colon",
        ":missing_module",
        "missing_attr:",
    ],
    ids=["no_colon", "empty_module", "empty_attr"],
)
def test_load_target_rejects_malformed_reference(reference: str) -> None:
    with pytest.raises(CLIError):
        load_target(reference)


def test_load_target_reports_missing_module(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(CLIError, match="cannot import module"):
        load_target("definitely_not_a_real_module:obj")


def test_load_target_reports_missing_attribute(sample_app: str) -> None:
    with pytest.raises(CLIError, match="has no attribute"):
        load_target(f"{sample_app}:does_not_exist")


def test_asyncapi_gen_emits_json(runner: CliRunner, sample_app: str) -> None:
    result = runner.invoke(cli, ["asyncapi", "gen", f"{sample_app}:broker", "--title", "T"])
    assert result.exit_code == 0, result.output
    spec = json.loads(result.output)
    assert spec["info"] == {"title": "T", "version": "0.0.1"}
    assert spec["channels"]["orders"]["address"] == "orders"


def test_asyncapi_gen_writes_to_file_when_output_given(
    runner: CliRunner,
    sample_app: str,
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "spec.json"
    result = runner.invoke(cli, ["asyncapi", "gen", f"{sample_app}:broker", "-o", str(out_path)])
    assert result.exit_code == 0
    assert out_path.exists()
    assert "info" in json.loads(out_path.read_text())


@pytest.mark.skipif(not _has_yaml(), reason="PyYAML not installed")
def test_asyncapi_gen_emits_yaml(runner: CliRunner, sample_app: str) -> None:
    result = runner.invoke(cli, ["asyncapi", "gen", f"{sample_app}:broker", "--format", "yaml"])
    assert result.exit_code == 0
    assert "asyncapi:" in result.output
    assert "channels:" in result.output


def test_asyncapi_gen_reports_loader_errors_cleanly(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["asyncapi", "gen", "no_colon"])
    assert result.exit_code != 0
    assert "module" in result.output.lower()


def test_new_command_scaffolds_project(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(cli, ["new", "sample_svc", "--directory", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sample_svc" / "__init__.py").exists()
    assert (tmp_path / "sample_svc" / "__main__.py").exists()


def test_new_command_refuses_existing_directory(runner: CliRunner, tmp_path: Path) -> None:
    (tmp_path / "sample_svc").mkdir()
    result = runner.invoke(cli, ["new", "sample_svc", "--directory", str(tmp_path)])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_scaffold_helper_returns_created_files(tmp_path: Path) -> None:
    files = scaffold("svc_x", directory=tmp_path)
    assert all(f.exists() for f in files)
