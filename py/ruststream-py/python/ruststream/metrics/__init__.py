"""Prometheus metrics for RustStream brokers.

`PrometheusMetrics` is a self-contained bundle of counters and a histogram,
registered against either the supplied `CollectorRegistry` or a fresh one.
Pass the instance to a broker via the `metrics=` keyword to opt in:

    from ruststream import MemoryBroker
    from ruststream.metrics import PrometheusMetrics

    metrics = PrometheusMetrics()
    broker = MemoryBroker(metrics=metrics)

The broker calls into `record_*` hooks around each delivery; `metrics.export()`
returns the Prometheus exposition-format snapshot, ready to be served from any
HTTP framework. Requires `pip install ruststream[metrics]`.

Importing `ruststream.metrics` itself is dependency-free: `MetricsRecorder`,
`NullMetrics`, and the error class are always available. Touching
`PrometheusMetrics` triggers the import of the Prometheus adapter, which raises
:class:`MetricsMissingDependencyError` at import time if `prometheus_client` is
not installed -- the misconfiguration surfaces immediately, not on first use.
"""

from typing import TYPE_CHECKING, Any

from ruststream.metrics._base import MetricsRecorder, NullMetrics
from ruststream.metrics._errors import MetricsMissingDependencyError

if TYPE_CHECKING:
    from ruststream.metrics.prometheus import PrometheusMetrics


def __getattr__(name: str) -> Any:
    """Lazily import the Prometheus adapter on first attribute access."""
    if name == "PrometheusMetrics":
        from ruststream.metrics.prometheus import PrometheusMetrics

        globals()["PrometheusMetrics"] = PrometheusMetrics
        return PrometheusMetrics
    raise AttributeError(f"module 'ruststream.metrics' has no attribute {name!r}")


__all__: tuple[str, ...] = (
    "MetricsMissingDependencyError",
    "MetricsRecorder",
    "NullMetrics",
    "PrometheusMetrics",
)
