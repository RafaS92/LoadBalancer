"""Typed operational events and their publication boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from load_balancer.domain.models import Backend


@dataclass(frozen=True, slots=True)
class RequestCompleted:
    """One downstream request reached a terminal outcome."""

    method: str
    path: str
    status: int
    backend: Backend | None
    outcome: str
    duration_seconds: float
    request_id: str


@dataclass(frozen=True, slots=True)
class RetryAttempted:
    """One safe request will be attempted against another backend."""

    method: str
    reason: str
    failed_backend: Backend


@dataclass(frozen=True, slots=True)
class HealthChanged:
    """A backend crossed a configured health threshold."""

    backend_name: str
    healthy: bool
    reason: str
    threshold: int


@dataclass(frozen=True, slots=True)
class BackendOperatorStateChanged:
    """An operator changed whether a backend accepts new requests."""

    backend_name: str
    action: str
    enabled: bool
    draining: bool


OperationalEvent = (
    RequestCompleted
    | RetryAttempted
    | HealthChanged
    | BackendOperatorStateChanged
)


class EventSink(Protocol):
    """Receive typed application events without controlling use-case behavior."""

    def publish(self, event: OperationalEvent) -> None: ...


class NullEventSink:
    """Discard events when no operational adapters are configured."""

    def publish(self, event: OperationalEvent) -> None:
        del event
