"""Socket-free tests for proxy application orchestration."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from load_balancer.application.proxying import ProxyService
from load_balancer.domain.models import Backend
from load_balancer.domain.routing import RoundRobinPool
from load_balancer.ports.downstream import DeliveryResult
from load_balancer.ports.events import OperationalEvent, RetryAttempted
from load_balancer.ports.upstream import UpstreamFailure, UpstreamRequest


class FakeClock:
    def __init__(self) -> None:
        self.value = 1.0

    def now(self) -> float:
        self.value += 0.01
        return self.value


class RecordingEvents:
    def __init__(self) -> None:
        self.events: list[OperationalEvent] = []

    def publish(self, event: OperationalEvent) -> None:
        self.events.append(event)


class RecordingDownstream:
    def __init__(self) -> None:
        self.responses: list[tuple[int, bytes]] = []
        self.closed = False

    def send_body(
        self,
        status: int,
        body: bytes,
        *,
        request_id: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
        cache_control: str | None = None,
    ) -> bool:
        del request_id, content_type, cache_control
        self.responses.append((status, body))
        return True

    def send_upstream_headers(
        self,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        content_length: int,
        request_id: str,
    ) -> bool:
        del status, reason, headers, content_length, request_id
        return True

    def write_body(self, body: bytes) -> bool:
        del body
        return True

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeResponse:
    status: int = 200


class SequencedTransport:
    def __init__(self, outcomes: list[str | None]) -> None:
        self._outcomes = iter(outcomes)

    @contextmanager
    def send(
        self,
        backend: Backend,
        request: UpstreamRequest,
    ) -> Iterator[FakeResponse]:
        del backend, request
        outcome = next(self._outcomes)
        if outcome is not None:
            raise UpstreamFailure(outcome)
        yield FakeResponse()


class SuccessfulRelay:
    def relay(
        self,
        response: FakeResponse,
        request_id: str,
        downstream: RecordingDownstream,
    ) -> DeliveryResult:
        del request_id, downstream
        return DeliveryResult(response.status)


def request(method: str = "GET") -> UpstreamRequest:
    return UpstreamRequest(
        method=method,
        path="/items",
        body=None,
        headers=(),
        client_ip="127.0.0.1",
        original_host="localhost",
        request_id="request-1",
    )


def service(
    pool: RoundRobinPool,
    transport: SequencedTransport,
    events: RecordingEvents,
) -> ProxyService:
    return ProxyService(
        pool,
        transport,
        SuccessfulRelay(),
        events,
        FakeClock(),
        max_retries=1,
        retryable_methods=frozenset({"GET"}),
        retryable_outcomes=frozenset({"backend_connect_timeout"}),
    )


def test_retries_safe_failure_and_releases_every_backend() -> None:
    backends = [
        Backend("backend-a", "http://backend-a"),
        Backend("backend-b", "http://backend-b"),
    ]
    pool = RoundRobinPool(backends)
    events = RecordingEvents()
    proxy = service(
        pool,
        SequencedTransport(["backend_connect_timeout", None]),
        events,
    )

    result = proxy.execute(request(), RecordingDownstream())

    assert result.backend == backends[1]
    assert result.outcome == "completed_after_retry"
    assert [status.active_requests for status in pool.snapshot()] == [0, 0]
    assert any(isinstance(event, RetryAttempted) for event in events.events)


def test_does_not_retry_mutating_request() -> None:
    pool = RoundRobinPool(
        [
            Backend("backend-a", "http://backend-a"),
            Backend("backend-b", "http://backend-b"),
        ]
    )
    events = RecordingEvents()
    downstream = RecordingDownstream()
    proxy = service(
        pool,
        SequencedTransport(["backend_connect_timeout"]),
        events,
    )

    result = proxy.execute(request("POST"), downstream)

    assert result.backend is not None
    assert result.backend.name == "backend-a"
    assert result.outcome == "backend_connect_timeout"
    assert downstream.responses[0][0] == 502
    assert [status.active_requests for status in pool.snapshot()] == [0, 0]
