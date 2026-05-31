# ruststream (Python)

Python bindings for the [RustStream](../..) messaging framework.

## Install

The core wheel ships the in-memory broker and the dispatcher. Broker integrations are extras:

```bash
pip install ruststream            # core only
pip install ruststream[nats]      # core + NATS broker
```

## Develop locally

```bash
uv sync
uv run maturin develop --manifest-path py/ruststream-py/Cargo.toml
uv run maturin develop --manifest-path py/ruststream-nats-py/Cargo.toml  # if you need NATS
uv run pytest py/ruststream-py py/ruststream-nats-py
```
