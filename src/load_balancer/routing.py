"""Backend state and routing strategies.

The routing layer deliberately has no HTTP dependencies.  Keeping selection
separate from forwarding makes concurrency and failure behaviour easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol


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


class BackendPool(Protocol):
    """Operations required by proxying and health-checking components."""

    def acquire(self) -> Backend | None: ...

    def release(self, name: str) -> None: ...

    def set_health(self, name: str, *, healthy: bool) -> None: ...

    def set_enabled(self, name: str, *, enabled: bool) -> None: ...

    def begin_drain(self, name: str) -> None: ...

    def snapshot(self) -> tuple[BackendStatus, ...]: ...


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
        self._enabled = {backend.name: True for backend in backends}
        self._draining = {backend.name: False for backend in backends}
        self._active_requests = {backend.name: 0 for backend in backends}
        self._next_index = 0
        self._lock = Lock()

    def choose(self) -> Backend | None:
        """Return the next healthy backend, or ``None`` if none are healthy."""

        with self._lock:
            return self._choose_healthy_backend()

    def acquire(self) -> Backend | None:
        """Select a healthy backend and increment its active-request count."""

        with self._lock:
            backend = self._choose_healthy_backend()
            if backend is not None:
                self._active_requests[backend.name] += 1
            return backend

    def release(self, name: str) -> None:
        """Decrement a backend's active-request count after completion."""

        with self._lock:
            if name not in self._active_requests:
                raise KeyError(f"unknown backend: {name}")
            if self._active_requests[name] == 0:
                raise RuntimeError(f"backend has no active requests: {name}")
            self._active_requests[name] -= 1

    def set_health(self, name: str, *, healthy: bool) -> None:
        """Update whether health checks consider a backend healthy."""

        with self._lock:
            if name not in self._healthy:
                raise KeyError(f"unknown backend: {name}")
            self._healthy[name] = healthy

    def set_enabled(self, name: str, *, enabled: bool) -> None:
        """Update whether an operator allows new requests to a backend."""

        with self._lock:
            if name not in self._enabled:
                raise KeyError(f"unknown backend: {name}")
            self._enabled[name] = enabled
            self._draining[name] = False

    def begin_drain(self, name: str) -> None:
        """Stop new assignments while existing requests finish."""

        with self._lock:
            if name not in self._enabled:
                raise KeyError(f"unknown backend: {name}")
            self._enabled[name] = False
            self._draining[name] = True

    def snapshot(self) -> tuple[BackendStatus, ...]:
        """Return a consistent, read-only snapshot of all backend states."""

        with self._lock:
            return tuple(
                BackendStatus(
                    backend,
                    self._healthy[backend.name],
                    self._enabled[backend.name],
                    self._draining[backend.name],
                    self._active_requests[backend.name],
                )
                for backend in self._backends
            )

    def _choose_healthy_backend(self) -> Backend | None:
        """Choose the next healthy backend while the caller holds the lock."""

        for offset in range(len(self._backends)):
            index = (self._next_index + offset) % len(self._backends)
            backend = self._backends[index]
            if self._is_eligible(backend):
                self._next_index = (index + 1) % len(self._backends)
                return backend
        return None

    def _is_eligible(self, backend: Backend) -> bool:
        """Return whether health and operator state allow new requests."""

        return self._healthy[backend.name] and self._enabled[backend.name]


class LeastConnectionsPool(RoundRobinPool):
    """Select the healthy backend handling the fewest active requests."""

    def _choose_healthy_backend(self) -> Backend | None:
        """Choose the least busy backend, using round-robin to break ties."""

        eligible_backends = [
            backend for backend in self._backends if self._is_eligible(backend)
        ]
        if not eligible_backends:
            return None

        fewest_requests = min(
            self._active_requests[backend.name] for backend in eligible_backends
        )
        for offset in range(len(self._backends)):
            index = (self._next_index + offset) % len(self._backends)
            backend = self._backends[index]
            if (
                self._is_eligible(backend)
                and self._active_requests[backend.name] == fewest_requests
            ):
                self._next_index = (index + 1) % len(self._backends)
                return backend
        return None


def create_pool(backends: list[Backend], strategy: str) -> BackendPool:
    """Create the configured routing pool."""

    if strategy == "round-robin":
        return RoundRobinPool(backends)
    if strategy == "least-connections":
        return LeastConnectionsPool(backends)
    raise ValueError(f"unknown routing strategy: {strategy}")
