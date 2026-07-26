"""Port used by application services to communicate with backends."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from load_balancer.domain.models import Backend


@dataclass(frozen=True, slots=True)
class UpstreamRequest:
    """Request data required by an upstream transport."""

    method: str
    path: str
    body: bytes | None
    headers: tuple[tuple[str, str], ...]
    client_ip: str
    original_host: str | None
    request_id: str


class UpstreamResponse(Protocol):
    """Backend response operations needed by response delivery policy."""

    status: int
    reason: str
    chunked: bool

    def getheaders(self) -> list[tuple[str, str]]: ...

    def read(self, amount: int | None = None) -> bytes: ...

    def read1(self, amount: int = -1) -> bytes: ...


class UpstreamTransportPort(Protocol):
    """Open a bounded exchange with one selected backend."""

    def send(
        self,
        backend: Backend,
        request: UpstreamRequest,
    ) -> AbstractContextManager[UpstreamResponse]: ...


class UpstreamFailure(Exception):
    """Carry a stable operational outcome from an upstream adapter."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome
