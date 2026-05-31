"""Metrics-module errors."""


class MetricsMissingDependencyError(RuntimeError):
    """`prometheus_client` is not installed; install `ruststream[metrics]` to enable
    `PrometheusMetrics`."""

    def __init__(self) -> None:
        super().__init__(
            "PrometheusMetrics requires the 'prometheus_client' package "
            "(install via `pip install ruststream[metrics]`)",
        )


__all__: tuple[str, ...] = ("MetricsMissingDependencyError",)
