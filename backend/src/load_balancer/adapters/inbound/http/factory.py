"""Convenience composition for one standalone downstream HTTP adapter."""

from __future__ import annotations

from http.client import HTTPConnection

from load_balancer.adapters.inbound.http.handler import (
    ProxyHTTPServer,
    create_http_server,
)
from load_balancer.adapters.observability.events import (
    CompositeEventSink,
    DashboardEventSink,
    StructuredLogEventSink,
)
from load_balancer.adapters.observability.metrics import LoadBalancerMetrics
from load_balancer.adapters.outbound.http.response import ResponseRelay
from load_balancer.adapters.outbound.http.upstream import UpstreamTransport
from load_balancer.application.administration import ControlPlaneService
from load_balancer.application.dashboard import (
    DashboardReadModel,
    DashboardService,
)
from load_balancer.application.proxying import ProxyService
from load_balancer.domain.routing import BackendPool
from load_balancer.infrastructure.defaults import (
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    DEFAULT_MAX_RESPONSE_BODY_BYTES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_UPSTREAM_CONNECT_TIMEOUT,
    DEFAULT_UPSTREAM_RESPONSE_TIMEOUT,
    RETRYABLE_METHODS,
    RETRYABLE_OUTCOMES,
)
from load_balancer.infrastructure.runtime import SystemClock


def create_proxy_server(
    address: tuple[str, int],
    pool: BackendPool,
    *,
    upstream_connect_timeout: float = DEFAULT_UPSTREAM_CONNECT_TIMEOUT,
    upstream_response_timeout: float = DEFAULT_UPSTREAM_RESPONSE_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    max_response_body_bytes: int = DEFAULT_MAX_RESPONSE_BODY_BYTES,
) -> ProxyHTTPServer:
    """Compose the standard adapters around a caller-provided backend pool."""

    metrics = LoadBalancerMetrics()
    traffic = DashboardReadModel()
    events = CompositeEventSink(
        [
            metrics,
            DashboardEventSink(traffic),
            StructuredLogEventSink(),
        ]
    )
    control_plane = ControlPlaneService(pool, events)
    dashboard = DashboardService(control_plane, traffic)
    transport = UpstreamTransport(
        connect_timeout=upstream_connect_timeout,
        response_timeout=upstream_response_timeout,
        connection_factory=HTTPConnection,
    )
    response_relay = ResponseRelay(max_response_body_bytes)
    clock = SystemClock()
    proxy_service = ProxyService(
        pool,
        transport,
        response_relay,
        events,
        clock,
        max_retries=max_retries,
        retryable_methods=RETRYABLE_METHODS,
        retryable_outcomes=RETRYABLE_OUTCOMES,
    )
    return create_http_server(
        address,
        proxy_service=proxy_service,
        metrics=metrics,
        control_plane=control_plane,
        dashboard=dashboard,
        max_request_body_bytes=max_request_body_bytes,
        clock=clock,
    )
