"""Backend state and routing strategies.

The routing layer deliberately has no HTTP dependencies.  Keeping selection
separate from forwarding makes concurrency and failure behaviour easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


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


class RoundRobinPool:
    """Select healthy backends in round-robin order.

    A single lock protects both the selection cursor and health state.  This
    guarantees that concurrent callers advance the sequence exactly once per
    successful selection.
    """

    def __init__(self, backends: list[Backend]) -> None:
        if not backends:
            raise ValueError("at least one backend is required")

        names = [backend.name for backend in backends]
        if len(names) != len(set(names)):
            raise ValueError("backend names must be unique")

        self._backends = tuple(backends)
        self._healthy = {backend.name: True for backend in backends}
        self._next_index = 0
        self._lock = Lock()

    def choose(self) -> Backend | None:
        """Return the next healthy backend, or ``None`` if none are healthy."""

        with self._lock:
            for offset in range(len(self._backends)):
                index = (self._next_index + offset) % len(self._backends)
                backend = self._backends[index]
                if self._healthy[backend.name]:
                    self._next_index = (index + 1) % len(self._backends)
                    return backend
            return None

    def set_health(self, name: str, *, healthy: bool) -> None:
        """Update whether a backend is eligible for new requests."""

        with self._lock:
            if name not in self._healthy:
                raise KeyError(f"unknown backend: {name}")
            self._healthy[name] = healthy

    def snapshot(self) -> tuple[BackendStatus, ...]:
        """Return a consistent, read-only snapshot of all backend states."""

        with self._lock:
            return tuple(
                BackendStatus(backend, self._healthy[backend.name])
                for backend in self._backends
            )
