"""Prometheus metrics for proxied requests."""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest


class ProxyMetrics:
    """Own and update the metrics exported by one proxy server."""

    def __init__(self) -> None:
        self._registry = CollectorRegistry()
        self._requests = Counter(
            "load_balancer_proxy_requests_total",
            "Completed requests handled by the proxy",
            ("method", "status", "outcome", "backend"),
            registry=self._registry,
        )
        self._duration = Histogram(
            "load_balancer_proxy_request_duration_seconds",
            "Time spent selecting a backend and proxying a request",
            ("method", "outcome", "backend"),
            registry=self._registry,
        )

    def record(
        self,
        *,
        method: str,
        status: int,
        outcome: str,
        backend: str | None,
        duration_seconds: float,
    ) -> None:
        """Record one completed proxy request."""

        backend_label = backend or "none"
        self._requests.labels(
            method=method,
            status=str(status),
            outcome=outcome,
            backend=backend_label,
        ).inc()
        self._duration.labels(
            method=method,
            outcome=outcome,
            backend=backend_label,
        ).observe(duration_seconds)

    def render(self) -> bytes:
        """Render this server's registry in Prometheus text format."""

        return generate_latest(self._registry)
