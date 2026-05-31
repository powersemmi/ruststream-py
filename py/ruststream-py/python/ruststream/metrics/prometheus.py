"""Prometheus collectors. Requires `pip install ruststream[metrics]`.

`prometheus_client` is imported at module load with no fallback: if the package
is absent the import raises :class:`MetricsMissingDependencyError`, surfacing
the misconfiguration at the import site rather than at first use of the class.
"""

from typing import Any, ClassVar

from ruststream.failure import FailureAction
from ruststream.metrics._errors import MetricsMissingDependencyError

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
except ImportError as exc:
    raise MetricsMissingDependencyError() from exc


_DEFAULT_BUCKETS = (
    0.001,
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class PrometheusMetrics:
    """Bundle of Prometheus collectors covering broker dispatch.

    Metrics shape:
        * `ruststream_messages_received_total{topic}` counter.
        * `ruststream_messages_succeeded_total{topic}` counter.
        * `ruststream_messages_failed_total{topic,action,exception}` counter.
        * `ruststream_handler_duration_seconds{topic}` histogram.

    The metrics register on the supplied `CollectorRegistry` (default: a fresh
    private registry, so tests do not pollute the global one). Pass
    `prometheus_client.REGISTRY` to share with the rest of the process.
    """

    name: ClassVar[str] = "prometheus"

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        *,
        namespace: str = "ruststream",
        duration_buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
    ) -> None:
        self._registry = registry if registry is not None else CollectorRegistry()
        self.registry: Any = self._registry

        common: dict[str, Any] = {"namespace": namespace, "registry": self._registry}

        self.messages_received = Counter(
            "messages_received_total",
            "Number of deliveries observed by the broker.",
            ("topic",),
            **common,
        )
        self.messages_succeeded = Counter(
            "messages_succeeded_total",
            "Number of deliveries whose handler returned cleanly.",
            ("topic",),
            **common,
        )
        self.messages_failed = Counter(
            "messages_failed_total",
            "Number of deliveries whose handler raised an exception.",
            ("topic", "action", "exception"),
            **common,
        )
        self.handler_duration = Histogram(
            "handler_duration_seconds",
            "Handler execution time, including DI and codec/validator work.",
            ("topic",),
            buckets=duration_buckets,
            **common,
        )

    def record_received(self, topic: str) -> None:
        self.messages_received.labels(topic=topic).inc()

    def record_success(self, topic: str, duration_s: float) -> None:
        self.messages_succeeded.labels(topic=topic).inc()
        self.handler_duration.labels(topic=topic).observe(duration_s)

    def record_failure(
        self,
        topic: str,
        action: FailureAction,
        exception_type: str,
    ) -> None:
        self.messages_failed.labels(
            topic=topic,
            action=action.value,
            exception=exception_type,
        ).inc()

    def export(self) -> bytes:
        """Return the current snapshot in Prometheus exposition format."""
        snapshot: bytes = generate_latest(self._registry)
        return snapshot


__all__: tuple[str, ...] = ("PrometheusMetrics",)
