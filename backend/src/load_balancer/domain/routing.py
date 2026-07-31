"""Thread-safe backend state and independently replaceable routing policies."""

from __future__ import annotations

from threading import Lock
from typing import Protocol

from load_balancer.domain.models import Backend, BackendStatus


class BackendPool(Protocol):
    """Operations required by proxying and health-checking use cases."""

    def acquire(self, *, exclude: set[str] | None = None) -> Backend | None: ...

    def release(self, name: str) -> None: ...

    def set_health(self, name: str, *, healthy: bool) -> None: ...

    def set_enabled(self, name: str, *, enabled: bool) -> None: ...

    def begin_drain(self, name: str) -> None: ...

    def snapshot(self) -> tuple[BackendStatus, ...]: ...


class RoutingPolicy(Protocol):
    """Choose one eligible backend index without mutating backend state."""

    def select(
        self,
        *,
        backends: tuple[Backend, ...],
        eligible_indices: tuple[int, ...],
        active_requests: dict[str, int],
        next_index: int,
    ) -> int | None: ...


class RoundRobinPolicy:
    """Select the first eligible backend at or after the shared cursor."""

    def select(
        self,
        *,
        backends: tuple[Backend, ...],
        eligible_indices: tuple[int, ...],
        active_requests: dict[str, int],
        next_index: int,
    ) -> int | None:
        del active_requests
        eligible = set(eligible_indices)
        for offset in range(len(backends)):
            index = (next_index + offset) % len(backends)
            if index in eligible:
                return index
        return None


class LeastConnectionsPolicy:
    """Select the least busy backend, using the cursor to break ties."""

    def select(
        self,
        *,
        backends: tuple[Backend, ...],
        eligible_indices: tuple[int, ...],
        active_requests: dict[str, int],
        next_index: int,
    ) -> int | None:
        if not eligible_indices:
            return None
        fewest_requests = min(
            active_requests[backends[index].name] for index in eligible_indices
        )
        eligible = {
            index
            for index in eligible_indices
            if active_requests[backends[index].name] == fewest_requests
        }
        for offset in range(len(backends)):
            index = (next_index + offset) % len(backends)
            if index in eligible:
                return index
        return None


class StatefulBackendPool:
    """Own mutable backend state and apply one routing policy."""

    def __init__(
        self,
        backends: list[Backend],
        policy: RoutingPolicy,
    ) -> None:
        if not backends:
            raise ValueError("at least one backend is required")
        names = [backend.name for backend in backends]
        if len(names) != len(set(names)):
            raise ValueError("backend names must be unique")

        self._backends = tuple(backends)
        self._policy = policy
        self._healthy = {backend.name: True for backend in backends}
        self._enabled = {backend.name: True for backend in backends}
        self._draining = {backend.name: False for backend in backends}
        self._active_requests = {backend.name: 0 for backend in backends}
        self._next_index = 0
        self._lock = Lock()

    def choose(self) -> Backend | None:
        """Choose without changing the active-request count."""

        with self._lock:
            return self._choose_backend()

    def acquire(self, *, exclude: set[str] | None = None) -> Backend | None:
        """Choose a backend and atomically record one active request."""

        with self._lock:
            backend = self._choose_backend(exclude)
            if backend is not None:
                self._active_requests[backend.name] += 1
            return backend

    def release(self, name: str) -> None:
        """Release a matching active request."""

        with self._lock:
            if name not in self._active_requests:
                raise KeyError(f"unknown backend: {name}")
            if self._active_requests[name] == 0:
                raise RuntimeError(f"backend has no active requests: {name}")
            self._active_requests[name] -= 1

    def set_health(self, name: str, *, healthy: bool) -> None:
        """Update health-check state."""

        with self._lock:
            self._require_backend(name)
            self._healthy[name] = healthy

    def set_enabled(self, name: str, *, enabled: bool) -> None:
        """Apply an operator enable or disable decision."""

        with self._lock:
            self._require_backend(name)
            self._enabled[name] = enabled
            self._draining[name] = False

    def begin_drain(self, name: str) -> None:
        """Stop new assignments while current requests finish."""

        with self._lock:
            self._require_backend(name)
            self._enabled[name] = False
            self._draining[name] = True

    def snapshot(self) -> tuple[BackendStatus, ...]:
        """Return one ordered, immutable state snapshot."""

        with self._lock:
            return tuple(
                BackendStatus(
                    backend=backend,
                    healthy=self._healthy[backend.name],
                    enabled=self._enabled[backend.name],
                    draining=self._draining[backend.name],
                    active_requests=self._active_requests[backend.name],
                )
                for backend in self._backends
            )

    def _choose_backend(
        self,
        exclude: set[str] | None = None,
    ) -> Backend | None:
        eligible_indices = tuple(
            index
            for index, backend in enumerate(self._backends)
            if self._healthy[backend.name]
            and self._enabled[backend.name]
            and (exclude is None or backend.name not in exclude)
        )
        selected = self._policy.select(
            backends=self._backends,
            eligible_indices=eligible_indices,
            active_requests=self._active_requests,
            next_index=self._next_index,
        )
        if selected is None:
            return None
        self._next_index = (selected + 1) % len(self._backends)
        return self._backends[selected]

    def _require_backend(self, name: str) -> None:
        if name not in self._healthy:
            raise KeyError(f"unknown backend: {name}")


class RoundRobinPool(StatefulBackendPool):
    """Compatibility pool configured with round-robin routing."""

    def __init__(self, backends: list[Backend]) -> None:
        super().__init__(backends, RoundRobinPolicy())


class LeastConnectionsPool(StatefulBackendPool):
    """Compatibility pool configured with least-connections routing."""

    def __init__(self, backends: list[Backend]) -> None:
        super().__init__(backends, LeastConnectionsPolicy())


def create_pool(backends: list[Backend], strategy: str) -> BackendPool:
    """Create the requested routing pool."""

    if strategy == "round-robin":
        return RoundRobinPool(backends)
    if strategy == "least-connections":
        return LeastConnectionsPool(backends)
    raise ValueError(f"unknown routing strategy: {strategy}")
