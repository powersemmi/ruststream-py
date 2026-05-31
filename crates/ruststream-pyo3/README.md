# ruststream-pyo3

Shared Rust helpers used by every RustStream Python binding wheel (`ruststream`,
`ruststream-nats`, future broker wheels). Not a Python package itself; provides:

- `runtime::install` - one-shot Tokio runtime registration for `pyo3-async-runtimes`.
- `to_pyerr` - convert any `Display` error into a Python `RuntimeError`.
- `PyIncomingMessage` trait with a blanket impl over `IncomingMessage`, plus
  `pump_subscriber` to drive any `Subscriber::stream()` into an mpsc channel consumed by a
  Python async iterator.

Wheels define their own `#[pyclass]` types for `Message` / `Subscriber` so each wheel exposes
classes inside its own module, but the underlying machinery is shared.
