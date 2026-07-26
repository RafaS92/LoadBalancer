"""Standard composition of probing, evaluation, metrics, and scheduling."""

from __future__ import annotations

import httpx

from load_balancer.adapters.observability.events import (
    CompositeEventSink,
    StructuredLogEventSink,
)
from load_balancer.adapters.observability.metrics import LoadBalancerMetrics
from load_balancer.adapters.outbound.http.health_probe import HttpHealthProbe
from load_balancer.application.health import HealthEvaluationService
from load_balancer.domain.routing import BackendPool
from load_balancer.infrastructure.defaults import (
    DEFAULT_HEALTH_FAILURE_THRESHOLD,
    DEFAULT_HEALTH_INTERVAL,
    DEFAULT_HEALTH_PATH,
    DEFAULT_HEALTH_SUCCESS_THRESHOLD,
    DEFAULT_HEALTH_TIMEOUT,
)
from load_balancer.infrastructure.health_worker import ThreadedHealthWorker
from load_balancer.ports.events import EventSink


class HealthChecker:
    """Provide a convenient complete health-check subsystem."""

    def __init__(
        self,
        pool: BackendPool,
        *,
        path: str = DEFAULT_HEALTH_PATH,
        interval: float = DEFAULT_HEALTH_INTERVAL,
        timeout: float = DEFAULT_HEALTH_TIMEOUT,
        failure_threshold: int = DEFAULT_HEALTH_FAILURE_THRESHOLD,
        success_threshold: int = DEFAULT_HEALTH_SUCCESS_THRESHOLD,
        metrics: LoadBalancerMetrics | None = None,
        client: httpx.Client | None = None,
        events: EventSink | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("health interval and timeout must be positive")
        health_metrics = metrics or LoadBalancerMetrics()
        event_sink = events or CompositeEventSink(
            [health_metrics, StructuredLogEventSink()]
        )
        for status in pool.snapshot():
            health_metrics.set_backend_health(
                status.backend.name,
                healthy=status.healthy,
            )
        evaluator = HealthEvaluationService(
            pool,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            events=event_sink,
        )
        probe = HttpHealthProbe(timeout=timeout, client=client)
        self._worker = ThreadedHealthWorker(
            pool,
            probe,
            evaluator,
            path=path,
            interval=interval,
        )

    def check_once(self) -> None:
        self._worker.check_once()

    def start(self) -> None:
        self._worker.start()

    def stop(self) -> None:
        self._worker.stop()
