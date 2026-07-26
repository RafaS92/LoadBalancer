"""Convenient application-level exports for commands and events."""

from __future__ import annotations

from dataclasses import dataclass

from load_balancer.domain.models import Backend
from load_balancer.ports.events import (
    BackendOperatorStateChanged,
    HealthChanged,
    OperationalEvent,
    RequestCompleted,
    RetryAttempted,
)
from load_balancer.ports.upstream import UpstreamRequest

ProxyRequest = UpstreamRequest


@dataclass(frozen=True, slots=True)
class ProxyResult:
    """Final classified result of one proxy use case."""

    status: int
    backend: Backend | None
    outcome: str


__all__ = [
    "BackendOperatorStateChanged",
    "HealthChanged",
    "OperationalEvent",
    "ProxyRequest",
    "ProxyResult",
    "RequestCompleted",
    "RetryAttempted",
]
