"""In-process broker that keeps every message in memory.

`MemoryBroker` is a real, usable broker: each subscriber receives every message published to
its topic after the subscription was opened, with no durability and no network. Use it for
single-process applications, prototypes, examples and local development, as well as for tests
of router / handler / codec logic that do not depend on broker-specific semantics. For broker
semantics (durable consumers, offsets, exchanges) install the matching broker wheel.
"""

from typing import Any

from ruststream._broker import Broker, Router
from ruststream._interfaces import Subscriber
from ruststream._native import MemoryBroker as _RawMemoryBroker
from ruststream.codecs import Codec
from ruststream.di import DI
from ruststream.failure import FailurePolicy
from ruststream.metrics import MetricsRecorder


class MemoryBroker(Broker):
    """In-process broadcast broker backed by the native in-memory transport."""

    def __init__(
        self,
        *,
        on_error: FailurePolicy = None,
        codec: Codec | str | None = None,
        di: DI | None = None,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        super().__init__(on_error=on_error, codec=codec, di=di, metrics=metrics)
        self._raw: _RawMemoryBroker | None = None

    async def _open(self) -> None:
        self._raw = _RawMemoryBroker()
        self._context.set_session("broker", "memory")
        self._context.set_session("broker_id", id(self._raw))

    async def _close(self) -> None:
        if self._raw is not None:
            await self._raw.shutdown()
            self._raw = None

    async def _subscribe(self, topic: str, **options: Any) -> Subscriber:
        # MemoryBroker has no broker-specific subscription options; kwargs are accepted to
        # match the Broker contract but ignored.
        del options
        if self._raw is None:
            raise RuntimeError("MemoryBroker is not started; call start() first")
        subscriber: Subscriber = await self._raw.subscribe(topic)
        return subscriber

    async def _publish(self, topic: str, payload: bytes) -> None:
        if self._raw is None:
            self._raw = _RawMemoryBroker()
        await self._raw.publish(topic, payload)


class MemoryRouter(Router):
    """Reusable bundle of subscriber registrations for `MemoryBroker`."""


__all__: tuple[str, ...] = ("MemoryBroker", "MemoryRouter")
