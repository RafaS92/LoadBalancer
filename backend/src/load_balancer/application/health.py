"""Health threshold evaluation independent of probing and scheduling."""

from __future__ import annotations

from load_balancer.domain.routing import BackendPool
from load_balancer.ports.events import EventSink, HealthChanged, NullEventSink


class HealthEvaluationService:
    """Turn consecutive probe results into backend health transitions."""

    def __init__(
        self,
        pool: BackendPool,
        *,
        failure_threshold: int,
        success_threshold: int,
        events: EventSink | None = None,
    ) -> None:
        if failure_threshold <= 0 or success_threshold <= 0:
            raise ValueError("health thresholds must be positive")
        self._pool = pool
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._events = events or NullEventSink()
        statuses = pool.snapshot()
        self._consecutive_failures = {
            status.backend.name: 0 for status in statuses
        }
        self._consecutive_successes = {
            status.backend.name: 0 for status in statuses
        }

    def apply(
        self,
        name: str,
        *,
        currently_healthy: bool,
        succeeded: bool,
    ) -> None:
        if succeeded:
            self._consecutive_failures[name] = 0
            if currently_healthy:
                self._consecutive_successes[name] = 0
                return
            self._consecutive_successes[name] += 1
            if self._consecutive_successes[name] >= self._success_threshold:
                self._pool.set_health(name, healthy=True)
                self._events.publish(
                    HealthChanged(
                        backend_name=name,
                        healthy=True,
                        reason="success_threshold_reached",
                        threshold=self._success_threshold,
                    )
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
            self._events.publish(
                HealthChanged(
                    backend_name=name,
                    healthy=False,
                    reason="failure_threshold_reached",
                    threshold=self._failure_threshold,
                )
            )
            self._consecutive_failures[name] = 0
