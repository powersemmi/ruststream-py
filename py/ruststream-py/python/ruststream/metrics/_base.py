"""Metrics protocol + builtin no-op implementation.

This module is dependency-free so importing :mod:`ruststream.metrics` (and the
broker that uses it) never requires `prometheus_client`. The Prometheus adapter
lives in :mod:`ruststream.metrics._prometheus`, which raises on import when the
package is missing -- no silent fallback.
"""

from typing import ClassVar, Protocol, runtime_checkable

from ruststream.failure import FailureAction


@runtime_checkable
class MetricsRecorder(Protocol):
    """Hook surface the broker calls for every delivery.

    Implementations are free to no-op (see :class:`NullMetrics`), forward to
    Prometheus (see :class:`PrometheusMetrics`), or push to any other observability
    backend without touching broker code.
    """

    def record_received(self, topic: str) -> None:
        """Counter bump: a message just arrived for `topic`."""
        ...

    def record_success(self, topic: str, duration_s: float) -> None:
        """Counter bump + histogram observation: handler returned cleanly."""
        ...

    def record_failure(
        self,
        topic: str,
        action: FailureAction,
        exception_type: str,
    ) -> None:
        """Counter bump: handler raised; `action` is the policy the broker applied."""
        ...


class NullMetrics:
    """`MetricsRecorder` that does nothing; the default when no metrics are configured."""

    name: ClassVar[str] = "null"

    def record_received(self, topic: str) -> None:
        del topic

    def record_success(self, topic: str, duration_s: float) -> None:
        del topic, duration_s

    def record_failure(
        self,
        topic: str,
        action: FailureAction,
        exception_type: str,
    ) -> None:
        del topic, action, exception_type


__all__: tuple[str, ...] = ("MetricsRecorder", "NullMetrics")
