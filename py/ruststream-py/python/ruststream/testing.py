"""Test-only utilities exposed to Python users.

`BrokerTestClient` and `StubTransport` define the contract every broker package follows to
ship a test client; see `ruststream._testing`. `TestMemoryBroker` is the test client for the
in-memory `ruststream.memory.MemoryBroker` (which is itself a real broker, not test-only).
"""

from ruststream._native import MemoryBroker as _RawMemoryBroker
from ruststream._testing import BrokerTestClient, PublishedMessage, StubTransport


class TestMemoryBroker(BrokerTestClient):
    """`BrokerTestClient` for `MemoryBroker`, backed by the native in-memory transport."""

    _SESSION_LABEL = "memory-test"

    def _make_stub(self) -> StubTransport:
        stub: StubTransport = _RawMemoryBroker()
        return stub


__all__: tuple[str, ...] = (
    "BrokerTestClient",
    "PublishedMessage",
    "StubTransport",
    "TestMemoryBroker",
)
