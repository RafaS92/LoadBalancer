"""Port used by application services to deliver responses to clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from load_balancer.ports.upstream import UpstreamResponse


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Result of delivering one upstream response downstream."""

    status: int
    outcome: str | None = None


class DownstreamWriter(Protocol):
    """Transport-neutral response operations exposed by an inbound adapter."""

    def send_body(
        self,
        status: int,
        body: bytes,
        *,
        request_id: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
        cache_control: str | None = None,
    ) -> bool: ...

    def send_upstream_headers(
        self,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        content_length: int,
        request_id: str,
    ) -> bool: ...

    def write_body(self, body: bytes) -> bool: ...

    def close(self) -> None: ...


class ResponseRelayPort(Protocol):
    """Deliver one upstream response through the downstream adapter."""

    def relay(
        self,
        response: UpstreamResponse,
        request_id: str,
        downstream: DownstreamWriter,
    ) -> DeliveryResult: ...
