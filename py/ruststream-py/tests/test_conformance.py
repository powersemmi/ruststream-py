"""The conformance harness runs against the in-memory `MemoryBroker`.

`MemoryBroker` is the framework's own broker, so this dogfoods the contract against the real
implementation. The second test confirms the harness actually fails a broker that drops
messages, proving the suite has teeth.
"""

import pytest
from ruststream import MemoryBroker
from ruststream.conformance import ConformanceError, run_conformance
from ruststream.testing import BrokerTestClient, StubTransport, TestMemoryBroker

pytestmark = pytest.mark.asyncio


async def test_memory_broker_passes_conformance() -> None:
    def make_client(**broker_kwargs: object) -> TestMemoryBroker:
        return TestMemoryBroker(MemoryBroker(**broker_kwargs))

    await run_conformance(make_client)


async def test_conformance_detects_a_broken_broker() -> None:
    """A transport that silently drops messages must fail the suite."""

    class _SilentStub:
        async def subscribe(self, topic: str, **options: object) -> object:
            del topic, options

            class _NeverYields:
                def __aiter__(self) -> "_NeverYields":
                    return self

                async def __anext__(self) -> object:
                    import asyncio

                    await asyncio.Event().wait()
                    raise StopAsyncIteration

                def close(self) -> None:
                    return None

            return _NeverYields()

        async def publish(self, topic: str, payload: bytes) -> None:
            del topic, payload

        async def expect_published(
            self,
            topic: str,
            count: int,
            timeout_secs: float,
        ) -> list[object]:
            del topic, count, timeout_secs
            return []

        async def shutdown(self) -> None:
            return None

    class _TestSilentBroker(BrokerTestClient):
        _SESSION_LABEL = "silent-test"

        def _make_stub(self) -> StubTransport:
            stub: StubTransport = _SilentStub()
            return stub

    def make_client(**broker_kwargs: object) -> _TestSilentBroker:
        return _TestSilentBroker(MemoryBroker(**broker_kwargs))

    with pytest.raises(ConformanceError):
        await run_conformance(make_client)
