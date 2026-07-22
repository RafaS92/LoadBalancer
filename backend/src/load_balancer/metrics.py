"""Prometheus metrics for the load balancer."""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


class LoadBalancerMetrics:
    """Own and update metrics exported by one load-balancer process."""

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
        self._backend_healthy = Gauge(
            "load_balancer_backend_healthy",
            "Whether a configured backend is currently healthy",
            ("backend",),
            registry=self._registry,
        )
        self._health_transitions = Counter(
            "load_balancer_backend_health_transitions_total",
            "Backend transitions into healthy or unhealthy state",
            ("backend", "state"),
            registry=self._registry,
        )
        self._retries = Counter(
            "load_balancer_proxy_retries_total",
            "Additional backend attempts made for safe proxy requests",
            ("method", "reason", "failed_backend"),
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

    def set_backend_health(self, backend: str, *, healthy: bool) -> None:
        """Set the current-health gauge without recording a transition."""

        self._backend_healthy.labels(backend=backend).set(1 if healthy else 0)

    def record_health_transition(self, backend: str, *, healthy: bool) -> None:
        """Update current health and count one state transition."""

        state = "healthy" if healthy else "unhealthy"
        self.set_backend_health(backend, healthy=healthy)
        self._health_transitions.labels(backend=backend, state=state).inc()

    def record_retry(self, method: str, reason: str, failed_backend: str) -> None:
        """Count one real additional attempt after a safe failure."""

        self._retries.labels(
            method=method,
            reason=reason,
            failed_backend=failed_backend,
        ).inc()

    def render(self) -> bytes:
        """Render this server's registry in Prometheus text format."""

        return generate_latest(self._registry)
