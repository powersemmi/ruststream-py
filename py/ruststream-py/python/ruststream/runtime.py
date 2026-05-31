"""Tokio runtime configuration for the native extension.

The Rust extension picks up its scheduler shape from environment variables read on
the first `import ruststream._native`. After that, the runtime is locked for the
lifetime of the process, so configuration must happen *before* any other
RustStream module imports the extension.

The expected usage for ASGI servers (uvicorn, hypercorn) is to call
:func:`configure_runtime` at the very top of your entry point, before importing
anything else from `ruststream`::

    # myapp.py
    from ruststream.runtime import configure_runtime

    configure_runtime(worker_threads=1)  # single-thread Tokio for uvicorn -w 1

    from ruststream import MemoryBroker  # runtime is built here

If the extension is already imported, :func:`configure_runtime` raises so a
silent misconfiguration is impossible. The helper just writes environment
variables; you can also set them in the shell (`RUSTSTREAM_TOKIO_WORKER_THREADS=1`
etc.) and skip this function entirely.
"""

import os
import sys

ENV_WORKER_THREADS = "RUSTSTREAM_TOKIO_WORKER_THREADS"
ENV_THREAD_NAME = "RUSTSTREAM_TOKIO_THREAD_NAME"


class RuntimeAlreadyStartedError(RuntimeError):
    """Raised when :func:`configure_runtime` is called too late to take effect."""

    def __init__(self) -> None:
        super().__init__(
            "the native Tokio runtime has already been built; call "
            "`configure_runtime(...)` before importing any other ruststream module",
        )


def _native_already_imported() -> bool:
    return "ruststream._native" in sys.modules


def configure_runtime(
    *,
    worker_threads: int | None = None,
    thread_name: str | None = None,
) -> None:
    """Set the Tokio runtime knobs read by the native extension on import.

    Args:
        worker_threads: When `1`, the extension uses Tokio's `current_thread` scheduler
            (lowest overhead, suitable for `uvicorn --workers 1` or any ASGI server
            that owns its own event loop). Higher values force a multi-thread
            scheduler with that many worker threads. `None` leaves the variable
            unset, so Tokio picks the worker count itself.
        thread_name: Prefix for Tokio worker thread names in multi-thread mode.
            Useful for tagging traces and `top` output. Ignored under
            `worker_threads=1`.

    Raises:
        RuntimeAlreadyStartedError: If the native extension has already been
            imported. Call this before any `from ruststream import ...` statement.
        ValueError: If `worker_threads` is set to a non-positive integer.
    """
    if _native_already_imported():
        raise RuntimeAlreadyStartedError()
    if worker_threads is not None:
        if worker_threads < 1:
            raise ValueError("worker_threads must be >= 1")
        os.environ[ENV_WORKER_THREADS] = str(worker_threads)
    if thread_name is not None:
        os.environ[ENV_THREAD_NAME] = thread_name


__all__: tuple[str, ...] = (
    "ENV_THREAD_NAME",
    "ENV_WORKER_THREADS",
    "RuntimeAlreadyStartedError",
    "configure_runtime",
)
