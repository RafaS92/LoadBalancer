"""Active backend health checking."""

from __future__ import annotations

import json
import logging
from threading import Event, Thread

import httpx

from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.routing import Backend, BackendPool

HEALTH_LOGGER = logging.getLogger("load_balancer.health")


class HealthChecker:
    """Periodically update a pool by probing every configured backend."""

    def __init__(
        self,
        pool: BackendPool,
        *,
        path: str = "/health",
        interval: float = 2.0,
        timeout: float = 0.5,
        failure_threshold: int = 2,
        success_threshold: int = 2,
        metrics: LoadBalancerMetrics | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not path.startswith("/"):
            raise ValueError("health path must start with /")
        if interval <= 0 or timeout <= 0:
            raise ValueError("health interval and timeout must be positive")
        if failure_threshold <= 0 or success_threshold <= 0:
            raise ValueError("health thresholds must be positive")

        self._pool = pool
        self._path = path
        self._interval = interval
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._metrics = metrics or LoadBalancerMetrics()
        initial_statuses = pool.snapshot()
        self._consecutive_failures = {
            status.backend.name: 0 for status in initial_statuses
        }
        self._consecutive_successes = {
            status.backend.name: 0 for status in initial_statuses
        }
        for status in initial_statuses:
            self._metrics.set_backend_health(
                status.backend.name,
                healthy=status.healthy,
            )
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._stop_event = Event()
        self._thread: Thread | None = None

    def check_once(self) -> None:
        """Run one complete health-check cycle."""

        for status in self._pool.snapshot():
            succeeded = self._probe(status.backend)
            self._apply_result(status.backend.name, status.healthy, succeeded)

    def start(self) -> None:
        """Start checking in a background thread."""

        if self._thread is not None:
            raise RuntimeError("health checker is already running")
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="backend-health-checker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background thread and wait for it to finish."""

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._owns_client:
            self._client.close()

    def _run(self) -> None:
        """Check immediately, then wait between later cycles."""

        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self._interval)

    def _probe(self, backend: Backend) -> bool:
        """Return whether one backend responds successfully to the health path."""

        try:
            response = self._client.get(f"{backend.url.rstrip('/')}{self._path}")
            return response.is_success
        except httpx.HTTPError:
            return False

    def _apply_result(
        self, name: str, currently_healthy: bool, succeeded: bool
    ) -> None:
        """Apply one probe result after enforcing consecutive thresholds."""

        if succeeded:
            self._consecutive_failures[name] = 0
            if currently_healthy:
                self._consecutive_successes[name] = 0
                return

            self._consecutive_successes[name] += 1
            if self._consecutive_successes[name] >= self._success_threshold:
                self._pool.set_health(name, healthy=True)
                self._record_transition(
                    name,
                    healthy=True,
                    reason="success_threshold_reached",
                    threshold=self._success_threshold,
                )
                self._consecutive_successes[name] = 0
            return

        self._consecutive_successes[name] = 0
        if not currently_healthy:
            self._consecutive_failures[name] = 0
            return

        self._consecutive_failures[name] += 1
        if self._consecutive_failures[name] >= self._failure_threshold:
            self._pool.set_health(name, healthy=False)
            self._record_transition(
                name,
                healthy=False,
                reason="failure_threshold_reached",
                threshold=self._failure_threshold,
            )
            self._consecutive_failures[name] = 0

    def _record_transition(
        self,
        name: str,
        *,
        healthy: bool,
        reason: str,
        threshold: int,
    ) -> None:
        """Record one meaningful backend state change."""

        self._metrics.record_health_transition(name, healthy=healthy)
        HEALTH_LOGGER.info(
            json.dumps(
                {
                    "event": "backend_health_changed",
                    "backend": name,
                    "healthy": healthy,
                    "reason": reason,
                    "threshold": threshold,
                },
                separators=(",", ":"),
            )
        )
