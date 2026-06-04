//! Tokio runtime singleton shared with `pyo3-async-runtimes`.
//!
//! Each Python wheel that depends on this crate has its own copy of the runtime statics, so
//! calling [`install_runtime`] from every wheel's `#[pymodule]` initializer is safe and
//! intended.
//!
//! # Configuration via environment variables
//!
//! The runtime is built once and locked for the lifetime of the process, so configuration
//! has to be in place *before* any `RustStream` native module is imported.
//!
//! * `RUSTSTREAM_TOKIO_WORKER_THREADS` -- positive integer pinning the number of worker
//!   threads. `1` gives a single worker thread (lowest footprint, suitable for ASGI servers
//!   like `uvicorn --workers 1`). Unset / zero / non-numeric values keep the default
//!   multi-thread scheduler with as many workers as Tokio picks heuristically. The runtime
//!   is always a multi-thread scheduler: `pyo3-async-runtimes` drives spawned futures from
//!   the runtime's own worker threads, so a `current_thread` runtime (which only progresses
//!   inside `block_on`) would leave those futures unpolled.
//! * `RUSTSTREAM_TOKIO_THREAD_NAME` -- string used as a prefix for worker thread names.
//!   Defaults to `ruststream-py`.

use std::sync::OnceLock;

use tokio::runtime::{Builder, Runtime};

static RUNTIME: OnceLock<Runtime> = OnceLock::new();

const ENV_WORKER_THREADS: &str = "RUSTSTREAM_TOKIO_WORKER_THREADS";
const ENV_THREAD_NAME: &str = "RUSTSTREAM_TOKIO_THREAD_NAME";

fn read_worker_threads() -> Option<usize> {
    std::env::var(ENV_WORKER_THREADS)
        .ok()
        .and_then(|raw| raw.trim().parse::<usize>().ok())
        .filter(|n| *n >= 1)
}

fn thread_name() -> String {
    std::env::var(ENV_THREAD_NAME).unwrap_or_else(|_| "ruststream-py".to_owned())
}

fn build_runtime() -> Runtime {
    let mut builder = Builder::new_multi_thread();
    if let Some(n) = read_worker_threads() {
        builder.worker_threads(n);
    }
    builder
        .enable_all()
        .thread_name(thread_name())
        .build()
        .expect("failed to build the multi-thread Tokio runtime")
}

/// Builds (once per shared object) a Tokio runtime and hands it to
/// `pyo3-async-runtimes`. See the module-level docs for the environment variables that
/// pick the scheduler flavour and worker count.
///
/// # Panics
///
/// Panics if the runtime cannot be built, or if `pyo3-async-runtimes` rejects the runtime
/// installation. Both indicate a programming error rather than a recoverable runtime fault.
pub fn install_runtime() {
    let runtime = RUNTIME.get_or_init(build_runtime);
    pyo3_async_runtimes::tokio::init_with_runtime(runtime)
        .expect("failed to install Tokio runtime for pyo3-async-runtimes");
}
