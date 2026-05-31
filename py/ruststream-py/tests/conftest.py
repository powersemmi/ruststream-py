"""Shared pytest fixtures for the `ruststream` Python wheel."""

import asyncio
import importlib.util
from collections.abc import Callable
from typing import Any

import pytest
from ruststream import FailureAction, MemoryBroker, MemoryRouter


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


@pytest.fixture
def is_installed() -> Callable[[str], bool]:
    """Return a callable that reports whether `pkg` is importable in the current env."""
    return _is_installed


@pytest.fixture
def memory_broker() -> MemoryBroker:
    """Fresh `MemoryBroker` with the default `RawBytesCodec`."""
    return MemoryBroker()


@pytest.fixture
def memory_broker_json() -> MemoryBroker:
    """Fresh `MemoryBroker` preconfigured with the JSON codec."""
    return MemoryBroker(codec="json")


@pytest.fixture
def memory_broker_requeue() -> MemoryBroker:
    """Fresh `MemoryBroker` configured to nack-requeue handler exceptions."""
    return MemoryBroker(on_error=FailureAction.REQUEUE)


@pytest.fixture
def memory_broker_factory() -> Callable[..., MemoryBroker]:
    """Factory returning a fresh `MemoryBroker` per call with arbitrary kwargs."""

    def make(**kwargs: Any) -> MemoryBroker:
        return MemoryBroker(**kwargs)

    return make


@pytest.fixture
def memory_router() -> MemoryRouter:
    """Fresh, empty `MemoryRouter` ready to be populated and included into a broker."""
    return MemoryRouter()


@pytest.fixture
def wait_event() -> Callable[..., Any]:
    """Awaiter that blocks on `event` for up to `timeout` seconds, default 1.0s.

    Wraps the common `await asyncio.wait_for(event.wait(), timeout=...)` boilerplate
    that every end-to-end dispatch test repeats.
    """

    async def _wait(event: asyncio.Event, timeout: float = 1.0) -> None:  # noqa: ASYNC109
        await asyncio.wait_for(event.wait(), timeout=timeout)

    return _wait
