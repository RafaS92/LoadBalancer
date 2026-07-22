"""Structured proxy events backed by process metrics and logs."""

from __future__ import annotations

import json
import logging
from time import perf_counter

from load_balancer.dashboard import DashboardReadModel
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.routing import Backend

REQUEST_LOGGER = logging.getLogger("load_balancer.requests")


class ProxyObserver:
    """Record proxy outcomes without coupling orchestration to exporters."""

    def __init__(
        self,
        metrics: LoadBalancerMetrics,
        dashboard: DashboardReadModel | None = None,
    ) -> None:
        self._metrics = metrics
        self._dashboard = dashboard

    def record_completion(
        self,
        *,
        method: str,
        path: str,
        status: int,
        backend: Backend | None,
        outcome: str,
        started_at: float,
        request_id: str,
    ) -> None:
        """Record metrics and one structured event for a finished request."""

        duration_seconds = perf_counter() - started_at
        backend_name = backend.name if backend is not None else None
        self._metrics.record(
            method=method,
            status=status,
            outcome=outcome,
            backend=backend_name,
            duration_seconds=duration_seconds,
        )
        if self._dashboard is not None:
            self._dashboard.record_completion(
                method=method,
                path=path,
                status=status,
                backend=backend,
                outcome=outcome,
                duration_seconds=duration_seconds,
                request_id=request_id,
            )
        REQUEST_LOGGER.info(
            json.dumps(
                {
                    "event": "proxy_request_completed",
                    "method": method,
                    "path": path,
                    "status": status,
                    "backend": backend_name,
                    "outcome": outcome,
                    "request_id": request_id,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
                separators=(",", ":"),
            )
        )

    def record_retry(
        self,
        method: str,
        reason: str,
        failed_backend: Backend,
    ) -> None:
        """Record one additional safe upstream attempt."""

        self._metrics.record_retry(method, reason, failed_backend.name)
        if self._dashboard is not None:
            self._dashboard.record_retry(failed_backend)
