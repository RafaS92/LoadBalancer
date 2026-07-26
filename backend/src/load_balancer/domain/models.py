"""Domain models shared by routing and application use cases."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Backend:
    """A backend server known to the load balancer."""

    name: str
    url: str


@dataclass(frozen=True, slots=True)
class BackendStatus:
    """An immutable view of a backend's current routing state."""

    backend: Backend
    healthy: bool
    enabled: bool
    draining: bool
    active_requests: int
