"""Shared test-client contract for broker packages.

Broker packages ship a test client by subclassing `BrokerTestClient` and providing one
`_make_stub()` method that returns their in-process transport (a `StubTransport`). All the
wrapper mechanics, lifecycle, transport patching and `expect_published` helper live here, so
every broker's test client behaves identically.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any, Protocol, TypedDict, runtime_checkable

from ruststream._broker import Broker
from ruststream._native import Subscriber


class PublishedMessage(TypedDict):
    """One entry returned by `BrokerTestClient.expect_published`."""

    topic: str
    payload: bytes
    headers: dict[str, bytes]


@runtime_checkable
class StubTransport(Protocol):
    """In-process transport a broker package ships for its test client.

    Reproduces only Core routing: topic / subject matching plus fanout to the subscribers
    registered after they opened, with ack/nack as broker-side no-ops (a nack with requeue
    re-delivers to the same subscriber), and a recorded log of published messages behind
    `expect_published`.

    It must NOT simulate broker-specific semantics (durable cursors, consumer-group offsets,
    exchange / routing-key bindings, dead-letter queues, redelivery timers, retention). Those
    are covered only by integration tests against a real server, never by the stub.
    """

    async def subscribe(self, topic: str, **options: Any) -> Subscriber:
        """Open a subscription on `topic`, honouring the same kwargs as the real broker."""
        ...

    async def publish(self, topic: str, payload: bytes) -> None:
        """Match `topic` against open subscriptions and fan the payload out to each."""
        ...

    async def expect_published(
        self,
        topic: str,
        count: int,
        timeout_secs: float,
    ) -> Sequence[Mapping[str, Any]]:
        """Return up to `count` recorded messages on `topic`, waiting `timeout_secs`.

        Each entry is a mapping with `topic`, `payload` and `headers` keys.
        """
        ...

    async def shutdown(self) -> None:
        """Drop every subscription and release the transport's resources."""
        ...


class BrokerTestClient(ABC):
    """Base class for broker test clients.

    Wraps a production broker and drives its lifecycle for tests. With `with_real=False`
    (default) it swaps the broker's transport for an in-process `StubTransport`, so `publish`
    routes messages straight to the registered handlers with no network; with
    `with_real=True` it leaves the transport untouched and connects to the real server. The
    broker's handlers, middleware, codec, DI and failure policy are used unchanged, so they
    are declared once and shared between tests and production.

    Subclasses implement `_make_stub()` and may set `_SESSION_LABEL`; everything else is
    provided here.

    Args:
        broker: The broker under test, already carrying its subscriber registrations.
        with_real: When `True`, connect to the real server instead of the in-process stub.
    """

    # Tell pytest this is not a test case despite a possible `Test` prefix on subclasses.
    __test__ = False

    _SESSION_LABEL = "test"
    _TRANSPORT_METHODS = ("_open", "_close", "_subscribe", "_publish")

    def __init__(self, broker: Broker, *, with_real: bool = False) -> None:
        self._broker = broker
        self._with_real = with_real
        self._stub: StubTransport | None = None

    @property
    def broker(self) -> Broker:
        """The wrapped broker. Register handlers on it before entering the context."""
        return self._broker

    @abstractmethod
    def _make_stub(self) -> StubTransport:
        """Return a fresh in-process transport for this broker. See `StubTransport`."""

    async def __aenter__(self) -> Broker:
        if not self._with_real:
            self._patch()
        await self._broker.start()
        return self._broker

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        await self._broker.stop()
        if not self._with_real:
            self._unpatch()

    def _patch(self) -> None:
        broker = self._broker
        stub = self._make_stub()
        self._stub = stub
        label = self._SESSION_LABEL

        async def _open() -> None:
            broker._context.set_session("broker", label)

        async def _close() -> None:
            await stub.shutdown()

        async def _subscribe(topic: str, **options: Any) -> Subscriber:
            return await stub.subscribe(topic, **options)

        async def _publish(topic: str, payload: bytes) -> None:
            await stub.publish(topic, payload)

        # Shadow the bound transport methods with instance attributes; the base Broker calls
        # self._open / self._subscribe / self._publish, so these closures take over.
        broker._open = _open  # type: ignore[method-assign]
        broker._close = _close  # type: ignore[method-assign]
        broker._subscribe = _subscribe  # type: ignore[method-assign]
        broker._publish = _publish  # type: ignore[method-assign]

    def _unpatch(self) -> None:
        instance_attrs = vars(self._broker)
        for name in self._TRANSPORT_METHODS:
            instance_attrs.pop(name, None)
        self._stub = None

    async def expect_published(
        self,
        topic: str,
        count: int,
        *,
        timeout_secs: float = 1.0,
    ) -> Sequence[PublishedMessage]:
        """Await up to `count` messages recorded on `topic` and return the recorded prefix.

        Returns whatever has been recorded by the time `timeout_secs` elapses; never blocks
        longer than the timeout.

        Raises:
            RuntimeError: When called with `with_real=True`. Real brokers keep no log of
                published messages, so assert by subscribing a handler to the topic instead.
        """
        if self._stub is None:
            raise RuntimeError(
                "expect_published is only available with with_real=False; against a real "
                "server, assert by subscribing a handler to the topic",
            )
        raw = await self._stub.expect_published(topic, count, timeout_secs)
        return [
            PublishedMessage(
                topic=entry["topic"],
                payload=entry["payload"],
                headers=dict(entry["headers"]),
            )
            for entry in raw
        ]


__all__: tuple[str, ...] = ("BrokerTestClient", "PublishedMessage", "StubTransport")
