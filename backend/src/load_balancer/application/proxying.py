"""Request proxying use case independent of the downstream HTTP server."""

from __future__ import annotations

from load_balancer.application.contracts import ProxyResult
from load_balancer.domain.models import Backend
from load_balancer.domain.routing import BackendPool
from load_balancer.ports.downstream import DownstreamWriter, ResponseRelayPort
from load_balancer.ports.events import (
    EventSink,
    RequestCompleted,
    RetryAttempted,
)
from load_balancer.ports.runtime import Clock
from load_balancer.ports.upstream import (
    UpstreamFailure,
    UpstreamRequest,
    UpstreamTransportPort,
)


class ProxyService:
    """Coordinate selection, retries, transport, delivery, and accounting."""

    def __init__(
        self,
        pool: BackendPool,
        transport: UpstreamTransportPort,
        response_relay: ResponseRelayPort,
        events: EventSink,
        clock: Clock,
        *,
        max_retries: int,
        retryable_methods: frozenset[str],
        retryable_outcomes: frozenset[str],
    ) -> None:
        self._pool = pool
        self._transport = transport
        self._response_relay = response_relay
        self._events = events
        self._clock = clock
        self._max_retries = max_retries
        self._retryable_methods = retryable_methods
        self._retryable_outcomes = retryable_outcomes

    def execute(
        self,
        request: UpstreamRequest,
        downstream: DownstreamWriter,
    ) -> ProxyResult:
        """Execute one request and return its terminal classified result."""

        started_at = self._clock.now()
        attempted_backends: set[str] = set()
        last_failure: UpstreamFailure | None = None
        failed_backend: Backend | None = None

        for attempt in range(self._max_retries + 1):
            backend = self._pool.acquire(exclude=attempted_backends)
            if backend is None:
                return self._handle_unavailable(
                    request,
                    downstream,
                    started_at,
                    last_failure,
                    failed_backend,
                )

            if last_failure is not None and failed_backend is not None:
                self._events.publish(
                    RetryAttempted(
                        method=request.method,
                        reason=last_failure.outcome,
                        failed_backend=failed_backend,
                    )
                )
            attempted_backends.add(backend.name)
            try:
                try:
                    with self._transport.send(backend, request) as response:
                        delivery = self._response_relay.relay(
                            response,
                            request.request_id,
                            downstream,
                        )
                except UpstreamFailure as failure:
                    if self._can_retry(request.method, failure, attempt):
                        last_failure = failure
                        failed_backend = backend
                        continue
                    downstream.send_body(
                        502,
                        b"Selected backend could not be reached\n",
                        request_id=request.request_id,
                    )
                    return self._complete(
                        request,
                        status=502,
                        backend=backend,
                        outcome=failure.outcome,
                        started_at=started_at,
                    )

                if delivery.outcome == "client_disconnected":
                    downstream.close()
                    return self._complete(
                        request,
                        status=499,
                        backend=backend,
                        outcome="client_disconnected",
                        started_at=started_at,
                    )
                if delivery.outcome is not None:
                    downstream.close()
                    return self._complete(
                        request,
                        status=502,
                        backend=backend,
                        outcome=delivery.outcome,
                        started_at=started_at,
                    )
                outcome = (
                    "completed_after_retry" if attempt > 0 else "completed"
                )
                return self._complete(
                    request,
                    status=delivery.status,
                    backend=backend,
                    outcome=outcome,
                    started_at=started_at,
                )
            finally:
                self._pool.release(backend.name)

        raise AssertionError("proxy attempt loop ended without a result")

    def record_client_disconnect(
        self,
        request: UpstreamRequest,
        *,
        started_at: float | None = None,
    ) -> ProxyResult:
        """Record a client disconnect detected before backend selection."""

        return self._complete(
            request,
            status=499,
            backend=None,
            outcome="client_disconnected",
            started_at=started_at if started_at is not None else self._clock.now(),
        )

    def record_rejection(
        self,
        request: UpstreamRequest,
        *,
        status: int,
        outcome: str,
        started_at: float | None = None,
    ) -> ProxyResult:
        """Record a framing or safety rejection handled by the HTTP adapter."""

        return self._complete(
            request,
            status=status,
            backend=None,
            outcome=outcome,
            started_at=started_at if started_at is not None else self._clock.now(),
        )

    def _handle_unavailable(
        self,
        request: UpstreamRequest,
        downstream: DownstreamWriter,
        started_at: float,
        failure: UpstreamFailure | None,
        failed_backend: Backend | None,
    ) -> ProxyResult:
        if failure is None:
            downstream.send_body(
                503,
                b"No healthy backends available\n",
                request_id=request.request_id,
            )
            return self._complete(
                request,
                status=503,
                backend=None,
                outcome="no_healthy_backend",
                started_at=started_at,
            )
        downstream.send_body(
            502,
            b"Selected backend could not be reached\n",
            request_id=request.request_id,
        )
        return self._complete(
            request,
            status=502,
            backend=failed_backend,
            outcome=failure.outcome,
            started_at=started_at,
        )

    def _can_retry(
        self,
        method: str,
        failure: UpstreamFailure,
        attempt: int,
    ) -> bool:
        return (
            method in self._retryable_methods
            and failure.outcome in self._retryable_outcomes
            and attempt < self._max_retries
        )

    def _complete(
        self,
        request: UpstreamRequest,
        *,
        status: int,
        backend: Backend | None,
        outcome: str,
        started_at: float,
    ) -> ProxyResult:
        self._events.publish(
            RequestCompleted(
                method=request.method,
                path=request.path,
                status=status,
                backend=backend,
                outcome=outcome,
                duration_seconds=self._clock.now() - started_at,
                request_id=request.request_id,
            )
        )
        return ProxyResult(
            status=status,
            backend=backend,
            outcome=outcome,
        )
