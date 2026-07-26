"""The process composition root for concrete load-balancer dependencies."""

from __future__ import annotations

from dataclasses import dataclass

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
from load_balancer.adapters.outbound.http.health_probe import HttpHealthProbe
from load_balancer.adapters.outbound.http.response import ResponseRelay
from load_balancer.adapters.outbound.http.upstream import UpstreamTransport
from load_balancer.application.administration import ControlPlaneService
from load_balancer.application.dashboard import (
    DashboardReadModel,
    DashboardService,
)
from load_balancer.application.health import HealthEvaluationService
from load_balancer.application.proxying import ProxyService
from load_balancer.domain.routing import create_pool
from load_balancer.infrastructure.config import Settings
from load_balancer.infrastructure.defaults import (
    DEFAULT_RECENT_REQUEST_LIMIT,
    RETRYABLE_METHODS,
    RETRYABLE_OUTCOMES,
)
from load_balancer.infrastructure.health_worker import ThreadedHealthWorker
from load_balancer.infrastructure.runtime import SystemClock


@dataclass(frozen=True, slots=True)
class LoadBalancerApplication:
    """Fully wired runtime components owned by one process."""

    server: ProxyHTTPServer
    health_checker: ThreadedHealthWorker
    control_plane: ControlPlaneService
    metrics: LoadBalancerMetrics
    dashboard: DashboardService


def build_application(settings: Settings) -> LoadBalancerApplication:
    """Construct every concrete adapter in one visible composition root."""

    pool = create_pool(list(settings.backends), settings.strategy)
    metrics = LoadBalancerMetrics()
    traffic = DashboardReadModel(
        recent_request_limit=DEFAULT_RECENT_REQUEST_LIMIT
    )
    events = CompositeEventSink(
        [
            metrics,
            DashboardEventSink(traffic),
            StructuredLogEventSink(),
        ]
    )
    control_plane = ControlPlaneService(pool, events)
    dashboard = DashboardService(control_plane, traffic)
    clock = SystemClock()
    transport = UpstreamTransport(
        connect_timeout=settings.upstream_connect_timeout,
        response_timeout=settings.upstream_response_timeout,
    )
    response_relay = ResponseRelay(settings.max_response_body_bytes)
    proxy_service = ProxyService(
        pool,
        transport,
        response_relay,
        events,
        clock,
        max_retries=settings.max_retries,
        retryable_methods=RETRYABLE_METHODS,
        retryable_outcomes=RETRYABLE_OUTCOMES,
    )
    for status in pool.snapshot():
        metrics.set_backend_health(
            status.backend.name,
            healthy=status.healthy,
        )
    health_evaluator = HealthEvaluationService(
        pool,
        failure_threshold=settings.health_failure_threshold,
        success_threshold=settings.health_success_threshold,
        events=events,
    )
    health_probe = HttpHealthProbe(timeout=settings.health_timeout)
    health_checker = ThreadedHealthWorker(
        pool,
        health_probe,
        health_evaluator,
        path=settings.health_path,
        interval=settings.health_interval,
    )
    server = create_http_server(
        (settings.listen_host, settings.listen_port),
        proxy_service=proxy_service,
        metrics=metrics,
        control_plane=control_plane,
        dashboard=dashboard,
        max_request_body_bytes=settings.max_request_body_bytes,
        clock=clock,
    )
    return LoadBalancerApplication(
        server=server,
        health_checker=health_checker,
        control_plane=control_plane,
        metrics=metrics,
        dashboard=dashboard,
    )
