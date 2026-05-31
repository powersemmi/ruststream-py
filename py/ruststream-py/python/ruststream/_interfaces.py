"""Structural contracts a broker implementation satisfies.

A broker package can be written in pure Python (wrapping `aiokafka`, `redis-py`, `aio-pika`,
...) with no Rust at all. These Protocols spell out exactly what the dispatch loop requires
from a broker's subscriber and message types, so a Python-only broker has a typed target to
implement against.

A `Broker` subclass returns a `Subscriber` from `_subscribe`; the dispatch loop iterates it
and hands each `IncomingMessage` to the handler chain.
"""

from collections.abc import AsyncIterator, Mapping
from typing import Protocol


class IncomingMessage(Protocol):
    """One broker delivery handed to the dispatch loop."""

    @property
    def payload(self) -> bytes:
        """Raw delivery bytes."""
        ...

    @property
    def headers(self) -> Mapping[str, bytes]:
        """Delivery headers, keys lower-cased to match the broker contract."""
        ...

    async def ack(self) -> None:
        """Acknowledge successful processing."""
        ...

    async def nack(self, requeue: bool = False) -> None:
        """Negatively acknowledge; `requeue=True` asks for redelivery."""
        ...


class Subscriber(Protocol):
    """An open subscription that yields deliveries until it is closed.

    The dispatch loop consumes it with `async for message in subscriber` and calls `close()`
    when the subscription is torn down (handler task cancelled, broker stopped).
    """

    def __aiter__(self) -> AsyncIterator[IncomingMessage]:
        """Return the async iterator over deliveries."""
        ...

    def close(self) -> None:
        """Stop the subscription and release its resources."""
        ...


__all__: tuple[str, ...] = ("IncomingMessage", "Subscriber")
