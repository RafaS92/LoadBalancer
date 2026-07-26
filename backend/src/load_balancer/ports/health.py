"""Port used to probe backend readiness."""

from typing import Protocol

from load_balancer.domain.models import Backend


class HealthProbe(Protocol):
    """Return whether a backend responds successfully to a health request."""

    def probe(self, backend: Backend, path: str) -> bool: ...

    def close(self) -> None: ...
