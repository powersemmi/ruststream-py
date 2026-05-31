set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set dotenv-load := false

export PATH := env("HOME") + "/.cargo/bin:" + env("HOME") + "/.local/bin:" + env("PATH")

host_triple := `rustc -vV | grep '^host:' | cut -d' ' -f2`

default: check

install:
    uv sync
    uv run maturin develop --manifest-path py/ruststream-py/Cargo.toml --target {{host_triple}}

check: rust-check py-check

rust-check:
    cargo fmt --all -- --check
    cargo clippy --workspace --all-targets --all-features -- -D warnings
    cargo check --workspace --all-targets --all-features

py-check:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy

test: py-test

py-test:
    uv run pytest

fmt:
    cargo fmt --all
    uv run ruff check --fix .
    uv run ruff format .

build:
    cargo build --workspace --release
    uv run maturin build --release --manifest-path py/ruststream-py/Cargo.toml --target {{host_triple}}

build-dev:
    uv run maturin develop --manifest-path py/ruststream-py/Cargo.toml --target {{host_triple}}

security: bandit semgrep zizmor

bandit:
    uv run bandit -r py -c pyproject.toml

semgrep:
    uv run semgrep scan --config "p/python" --config "p/security-audit" --error --quiet py

zizmor:
    uv run zizmor .github/workflows

typo:
    uv run codespell

clean:
    cargo clean
    rm -rf .venv dist wheels target py/*/target

ci: check test typo security
