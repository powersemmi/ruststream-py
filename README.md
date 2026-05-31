# ruststream-py

Python framework of RustStream. This repository contains two packages:

| Package | Kind | Registry |
|---|---|---|
| `ruststream-pyo3` | Rust helper crate (`PyIncomingMessage`, `to_pyerr`, Tokio runtime singleton, mpsc-pump utilities) consumed by every Python broker binding. | crates.io |
| `ruststream` | Python wheel. Broker, Router, Validator, Codec, DI (NoOp/Dishka/FastDepends/FastAPI), ContextRepo, FailureAction, AsyncAPI build, Prometheus metrics, click CLI, FastAPI mounts. | PyPI |

Layout:

```
ruststream-py/
├── crates/
│   └── ruststream-pyo3/
├── py/
│   └── ruststream-py/
│       ├── Cargo.toml      (PyO3 cdylib pulled into the wheel)
│       ├── pyproject.toml  (maturin metadata)
│       ├── src/
│       ├── python/ruststream/
│       └── tests/
├── Cargo.toml              (workspace)
└── pyproject.toml          (uv workspace, dev tooling, ruff/mypy/pytest)
```

The Rust crates (`ruststream-core`, `ruststream-runtime`, `ruststream-conformance`) are sourced from the sibling [`ruststream-rs`](https://github.com/ruststream/ruststream-rs) repository via path dependencies. Layout assumed: both repos cloned side by side. Path deps flip to crates.io ranges once `ruststream-core 0.1` is published.

## Quick start

```bash
just install
just check
just test
```

## License

Apache-2.0.
