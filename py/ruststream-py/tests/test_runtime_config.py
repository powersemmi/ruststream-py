"""Tokio runtime configuration helper (`ruststream.runtime`)."""

import os
import sys

import pytest
from ruststream.runtime import (
    ENV_THREAD_NAME,
    ENV_WORKER_THREADS,
    RuntimeAlreadyStartedError,
    configure_runtime,
)


def test_configure_runtime_sets_worker_threads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "ruststream._native", raising=False)
    monkeypatch.delenv(ENV_WORKER_THREADS, raising=False)
    configure_runtime(worker_threads=1)
    assert os.environ[ENV_WORKER_THREADS] == "1"


def test_configure_runtime_sets_thread_name_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "ruststream._native", raising=False)
    monkeypatch.delenv(ENV_THREAD_NAME, raising=False)
    configure_runtime(thread_name="my-prefix")
    assert os.environ[ENV_THREAD_NAME] == "my-prefix"


def test_configure_runtime_rejects_non_positive_worker_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "ruststream._native", raising=False)
    with pytest.raises(ValueError, match=">= 1"):
        configure_runtime(worker_threads=0)


def test_configure_runtime_raises_after_native_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `ruststream._native` is already in sys.modules, configuration is too late."""
    monkeypatch.setitem(sys.modules, "ruststream._native", object())
    with pytest.raises(RuntimeAlreadyStartedError):
        configure_runtime(worker_threads=1)
