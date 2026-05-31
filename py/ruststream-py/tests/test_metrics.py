"""Prometheus metrics: collector wiring + broker integration."""

import asyncio
import importlib.util
import sys
from collections.abc import Awaitable, Callable

import pytest
from ruststream import FailureAction, MemoryBroker, Message, RustStream
from ruststream.metrics import (
    MetricsMissingDependencyError,
    MetricsRecorder,
    NullMetrics,
    PrometheusMetrics,
)

pytestmark_async = pytest.mark.asyncio


def _has_prometheus() -> bool:
    return importlib.util.find_spec("prometheus_client") is not None


pytestmark_prom = pytest.mark.skipif(
    not _has_prometheus(),
    reason="prometheus_client not installed",
)


def test_null_metrics_implements_recorder_protocol() -> None:
    null = NullMetrics()
    assert isinstance(null, MetricsRecorder)
    null.record_received("t")
    null.record_success("t", 0.001)
    null.record_failure("t", FailureAction.NACK, "ValueError")


def test_prometheus_module_import_raises_when_dependency_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter module raises at import time, not lazily at first use,
    so misconfiguration surfaces immediately where it can be debugged."""
    monkeypatch.setitem(sys.modules, "prometheus_client", None)
    monkeypatch.delitem(sys.modules, "ruststream.metrics.prometheus", raising=False)
    import importlib

    with pytest.raises(MetricsMissingDependencyError):
        importlib.import_module("ruststream.metrics.prometheus")


@pytestmark_prom
def test_prometheus_collectors_register_on_private_registry() -> None:
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    metrics = PrometheusMetrics(registry=registry)
    metrics.record_received("orders")
    metrics.record_success("orders", 0.012)
    metrics.record_failure("orders", FailureAction.NACK, "ValueError")
    text = metrics.export().decode()
    assert 'messages_received_total{topic="orders"}' in text
    assert 'messages_succeeded_total{topic="orders"}' in text
    assert 'action="nack"' in text
    assert 'exception="ValueError"' in text


@pytestmark_prom
@pytestmark_async
async def test_broker_records_success_and_failure(
    memory_broker_factory: Callable[..., MemoryBroker],
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    metrics = PrometheusMetrics()
    broker = memory_broker_factory(metrics=metrics)

    ok_seen = asyncio.Event()
    fail_seen = asyncio.Event()

    @broker.subscriber("ok")
    async def handle_ok(_msg: Message) -> None:
        ok_seen.set()

    @broker.subscriber("boom")
    async def handle_boom(_msg: Message) -> None:
        fail_seen.set()
        raise RuntimeError("kaboom")

    async with RustStream(broker):
        await broker.publish("ok", b"x")
        await broker.publish("boom", b"x")
        await wait_event(ok_seen)
        await wait_event(fail_seen)

    text = metrics.export().decode()
    assert 'messages_received_total{topic="ok"} 1.0' in text
    assert 'messages_succeeded_total{topic="ok"} 1.0' in text
    assert 'topic="boom"' in text
    assert 'exception="RuntimeError"' in text
