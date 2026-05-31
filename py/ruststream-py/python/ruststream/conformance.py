"""Conformance suite every broker package runs against its test client.

A broker package - whether it binds a Rust broker or is written in pure Python on top of an
asyncio client - proves it honours the dispatch contract by running `run_conformance`
against its `BrokerTestClient`. The suite drives the broker in stub mode (no server), so it
exercises only Core routing: a published message reaches the matching handler, the full
middleware / codec / DI / failure pipeline runs, the handler's return value is forwarded by
`@publisher`, and `expect_published` records traffic.

It deliberately does NOT test broker-specific semantics (durable cursors, consumer-group
offsets, exchange bindings, dead-letter queues, retention, wildcard dialects). Those are the
broker's own concern and are covered by integration tests against a real server.

Usage:
    ```python
    import pytest

    from ruststream.conformance import run_conformance
    from ruststream_acme import AcmeBroker
    from ruststream_acme.testing import TestAcmeBroker

    @pytest.mark.asyncio
    async def test_acme_conformance() -> None:
        def make_client(**broker_kwargs: object) -> TestAcmeBroker:
            return TestAcmeBroker(AcmeBroker("acme://test", **broker_kwargs))

        await run_conformance(make_client)
    ```
"""

import asyncio
from collections.abc import Awaitable, Callable

from ruststream._broker import Router
from ruststream._message import Message
from ruststream._testing import BrokerTestClient
from ruststream.failure import FailureAction

ClientFactory = Callable[..., BrokerTestClient]

_DEFAULT_TIMEOUT = 1.0
_QUIET_WAIT = 0.1


class ConformanceError(AssertionError):
    """Raised when a broker test client fails a conformance scenario."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConformanceError(message)


async def _await_event(event: asyncio.Event, label: str) -> None:
    try:
        await asyncio.wait_for(event.wait(), timeout=_DEFAULT_TIMEOUT)
    except TimeoutError:
        raise ConformanceError(
            f"{label}: handler was not invoked within {_DEFAULT_TIMEOUT}s",
        ) from None


async def run_conformance(make_client: ClientFactory) -> None:
    """Run every scenario against fresh clients from `make_client`.

    Args:
        make_client: Builds a fresh `BrokerTestClient` per call, forwarding keyword arguments
            to the wrapped broker's constructor (the suite passes `on_error=...` to exercise
            failure policies). Each scenario gets its own client, so state cannot leak between
            scenarios.

    Raises:
        ConformanceError: On the first scenario that violates the contract.
    """
    scenarios: tuple[Callable[[ClientFactory], Awaitable[None]], ...] = (
        _delivery_reaches_handler,
        _messages_preserve_publish_order,
        _default_failure_does_not_redeliver,
        _requeue_redelivers_until_success,
        _publisher_return_is_forwarded,
        _router_registrations_are_adopted,
        _expect_published_records_publishes,
    )
    for scenario in scenarios:
        await scenario(make_client)


async def _delivery_reaches_handler(make_client: ClientFactory) -> None:
    client = make_client()
    received: list[bytes] = []
    seen = asyncio.Event()

    @client.broker.subscriber("conformance.deliver")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    async with client as broker:
        await broker.publish("conformance.deliver", b"hello")
        await _await_event(seen, "delivery_reaches_handler")

    _require(
        received == [b"hello"],
        f"delivery_reaches_handler: expected [b'hello'], got {received!r}",
    )


async def _messages_preserve_publish_order(make_client: ClientFactory) -> None:
    client = make_client()
    received: list[int] = []
    done = asyncio.Event()

    @client.broker.subscriber("conformance.order")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload)[0])
        if len(received) == 5:
            done.set()

    async with client as broker:
        for i in range(5):
            await broker.publish("conformance.order", bytes([i]))
        await _await_event(done, "messages_preserve_publish_order")

    _require(
        received == [0, 1, 2, 3, 4],
        f"messages_preserve_publish_order: expected [0..4], got {received!r}",
    )


async def _default_failure_does_not_redeliver(make_client: ClientFactory) -> None:
    client = make_client()
    attempts: list[bytes] = []

    @client.broker.subscriber("conformance.drop")
    async def handle(msg: Message) -> None:
        attempts.append(bytes(msg.payload))
        raise RuntimeError("boom")

    async with client as broker:
        await broker.publish("conformance.drop", b"once")
        await asyncio.sleep(_QUIET_WAIT)

    _require(
        attempts == [b"once"],
        f"default_failure_does_not_redeliver: expected one attempt, got {attempts!r}",
    )


async def _requeue_redelivers_until_success(make_client: ClientFactory) -> None:
    client = make_client(on_error=FailureAction.REQUEUE)
    attempts = 0
    succeeded = asyncio.Event()

    @client.broker.subscriber("conformance.requeue")
    async def handle(_msg: Message) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("first attempt fails")
        succeeded.set()

    async with client as broker:
        await broker.publish("conformance.requeue", b"retry")
        await _await_event(succeeded, "requeue_redelivers_until_success")

    _require(
        attempts >= 2,
        f"requeue_redelivers_until_success: expected redelivery, got {attempts} attempts",
    )


async def _publisher_return_is_forwarded(make_client: ClientFactory) -> None:
    client = make_client()
    responses: list[bytes] = []
    answered = asyncio.Event()

    @client.broker.subscriber("conformance.req")
    @client.broker.publisher("conformance.resp")
    async def handle_request(msg: Message) -> bytes:
        return b"re:" + bytes(msg.payload)

    @client.broker.subscriber("conformance.resp")
    async def handle_response(msg: Message) -> None:
        responses.append(bytes(msg.payload))
        answered.set()

    async with client as broker:
        await broker.publish("conformance.req", b"ping")
        await _await_event(answered, "publisher_return_is_forwarded")

    _require(
        responses == [b"re:ping"],
        f"publisher_return_is_forwarded: expected [b're:ping'], got {responses!r}",
    )


async def _router_registrations_are_adopted(make_client: ClientFactory) -> None:
    client = make_client()
    received: list[bytes] = []
    seen = asyncio.Event()
    bundle = Router()

    @bundle.subscriber("conformance.router")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    client.broker.include_router(bundle)

    async with client as broker:
        await broker.publish("conformance.router", b"via-router")
        await _await_event(seen, "router_registrations_are_adopted")

    _require(
        received == [b"via-router"],
        f"router_registrations_are_adopted: expected [b'via-router'], got {received!r}",
    )


async def _expect_published_records_publishes(make_client: ClientFactory) -> None:
    client = make_client()

    async with client as broker:
        await broker.publish("conformance.observe", b"first")
        await broker.publish("conformance.observe", b"second")
        observed = await client.expect_published("conformance.observe", count=2)

    _require(
        len(observed) == 2,
        f"expect_published_records_publishes: expected 2 messages, got {len(observed)}",
    )
    _require(
        observed[0]["payload"] == b"first" and observed[1]["payload"] == b"second",
        f"expect_published_records_publishes: payloads out of order: {observed!r}",
    )


__all__: tuple[str, ...] = ("ClientFactory", "ConformanceError", "run_conformance")
