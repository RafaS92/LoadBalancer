"""Application-level result values."""

from __future__ import annotations

from dataclasses import dataclass

from load_balancer.domain.models import Backend


@dataclass(frozen=True, slots=True)
class ProxyResult:
    """Final classified result of one proxy use case."""

    status: int
    backend: Backend | None
    outcome: str
