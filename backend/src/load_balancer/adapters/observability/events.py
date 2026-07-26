"""Fan-out, logging, and dashboard implementations of operational events."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

from load_balancer.application.dashboard import DashboardReadModel
from load_balancer.ports.events import (
    BackendOperatorStateChanged,
    EventSink,
    HealthChanged,
    OperationalEvent,
    RequestCompleted,
    RetryAttempted,
)

REQUEST_LOGGER = logging.getLogger("load_balancer.requests")
HEALTH_LOGGER = logging.getLogger("load_balancer.health")
ADMIN_LOGGER = logging.getLogger("load_balancer.admin")


class CompositeEventSink:
    """Publish each event to multiple independent operational adapters."""

    def __init__(self, sinks: Iterable[EventSink]) -> None:
        self._sinks = tuple(sinks)

    def publish(self, event: OperationalEvent) -> None:
        for sink in self._sinks:
            sink.publish(event)


class DashboardEventSink:
    """Project request events into the bounded dashboard read model."""

    def __init__(self, dashboard: DashboardReadModel) -> None:
        self._dashboard = dashboard

    def publish(self, event: OperationalEvent) -> None:
        if isinstance(event, RequestCompleted):
            self._dashboard.record_completion(
                method=event.method,
                path=event.path,
                status=event.status,
                backend=event.backend,
                outcome=event.outcome,
                duration_seconds=event.duration_seconds,
                request_id=event.request_id,
            )
        elif isinstance(event, RetryAttempted):
            self._dashboard.record_retry(event.failed_backend)


class StructuredLogEventSink:
    """Write stable, compact JSON for meaningful operational events."""

    def publish(self, event: OperationalEvent) -> None:
        if isinstance(event, RequestCompleted):
            REQUEST_LOGGER.info(
                json.dumps(
                    {
                        "event": "proxy_request_completed",
                        "method": event.method,
                        "path": event.path,
                        "status": event.status,
                        "backend": (
                            event.backend.name
                            if event.backend is not None
                            else None
                        ),
                        "outcome": event.outcome,
                        "request_id": event.request_id,
                        "duration_ms": round(
                            event.duration_seconds * 1000, 3
                        ),
                    },
                    separators=(",", ":"),
                )
            )
        elif isinstance(event, HealthChanged):
            HEALTH_LOGGER.info(
                json.dumps(
                    {
                        "event": "backend_health_changed",
                        "backend": event.backend_name,
                        "healthy": event.healthy,
                        "reason": event.reason,
                        "threshold": event.threshold,
                    },
                    separators=(",", ":"),
                )
            )
        elif isinstance(event, BackendOperatorStateChanged):
            ADMIN_LOGGER.info(
                json.dumps(
                    {
                        "event": "backend_operator_state_changed",
                        "backend": event.backend_name,
                        "action": event.action,
                        "enabled": event.enabled,
                        "draining": event.draining,
                    },
                    separators=(",", ":"),
                )
            )
