"""End-to-end coverage for `Broker(on_error=...)` failure policies."""

import asyncio
import contextlib
from collections.abc import Callable

import pytest
from ruststream import FailureAction, MemoryBroker, Message, RustStream
from ruststream.failure import FailurePolicy, resolve_failure_action

pytestmark = pytest.mark.asyncio


class _BoomError(ValueError):
    pass


@pytest.mark.parametrize(
    ("policy", "expected_attempts"),
    [
        pytest.param(None, 1, id="default-nack-drops"),
        pytest.param(FailureAction.NACK, 1, id="explicit-nack-drops"),
        pytest.param(FailureAction.ACK, 1, id="ack-swallows"),
        pytest.param(FailureAction.REQUEUE, 2, id="requeue-redelivers-once"),
    ],
)
async def test_failure_action_controls_handler_attempts(
    memory_broker_factory: Callable[..., MemoryBroker],
    policy: FailurePolicy,
    expected_attempts: int,
) -> None:
    attempts = 0
    seen = asyncio.Event()
    broker = memory_broker_factory(on_error=policy)

    @broker.subscriber("topic")
    async def handle(_msg: Message) -> None:
        nonlocal attempts
        attempts += 1
        if attempts >= expected_attempts:
            seen.set()
        raise _BoomError("kaboom")

    async with RustStream(broker):
        await broker.publish("topic", b"x")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(seen.wait(), timeout=0.5)

    assert attempts == expected_attempts


async def test_per_type_policy_routes_by_mro(
    memory_broker_factory: Callable[..., MemoryBroker],
) -> None:
    """A mapping policy picks the action by walking exception MRO; first match wins."""

    class CustomError(Exception):
        pass

    class DerivedError(CustomError):
        pass

    seen = {"child": asyncio.Event(), "other": asyncio.Event()}
    attempts: list[str] = []

    broker = memory_broker_factory(
        on_error={
            CustomError: FailureAction.ACK,
            Exception: FailureAction.REQUEUE,
        },
    )

    @broker.subscriber("child")
    async def handle_child(_msg: Message) -> None:
        attempts.append("child")
        seen["child"].set()
        raise DerivedError("derived")

    @broker.subscriber("other")
    async def handle_other(_msg: Message) -> None:
        attempts.append("other")
        if attempts.count("other") >= 2:
            seen["other"].set()
        raise RuntimeError("not in mapping by name, only by Exception base")

    async with RustStream(broker):
        await broker.publish("child", b"c")
        await broker.publish("other", b"o")
        await asyncio.wait_for(seen["child"].wait(), timeout=0.5)
        await asyncio.wait_for(seen["other"].wait(), timeout=0.5)

    assert attempts.count("child") == 1  # CustomError -> ACK, no redelivery
    assert attempts.count("other") == 2  # Exception -> REQUEUE, one redelivery


async def test_raise_action_terminates_dispatch_task(
    memory_broker_factory: Callable[..., MemoryBroker],
) -> None:
    """`FailureAction.RAISE` propagates out of `_dispatch`; the subscriber task fails
    but the broker stops cleanly under `async with RustStream(...)`."""
    seen = asyncio.Event()
    broker = memory_broker_factory(on_error=FailureAction.RAISE)

    @broker.subscriber("topic")
    async def handle(_msg: Message) -> None:
        seen.set()
        raise _BoomError("fatal")

    async with RustStream(broker):
        await broker.publish("topic", b"x")
        await asyncio.wait_for(seen.wait(), timeout=0.5)
        await asyncio.sleep(0)


def test_resolve_failure_action_walks_mro_then_falls_back_to_default() -> None:
    class BaseError(Exception):
        pass

    class ChildError(BaseError):
        pass

    by_base = resolve_failure_action(
        {BaseError: FailureAction.ACK},
        ChildError(),
        default=FailureAction.NACK,
    )
    assert by_base is FailureAction.ACK
    fallback = resolve_failure_action(
        {KeyError: FailureAction.ACK},
        ChildError(),
        default=FailureAction.REQUEUE,
    )
    assert fallback is FailureAction.REQUEUE
    assert resolve_failure_action(None, ChildError()) is FailureAction.NACK
    assert resolve_failure_action(FailureAction.REQUEUE, ChildError()) is FailureAction.REQUEUE
