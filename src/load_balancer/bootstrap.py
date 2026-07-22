"""Dependency composition for one load-balancer process."""

from __future__ import annotations

from dataclasses import dataclass

from load_balancer.config import Settings
from load_balancer.control_plane import ControlPlaneService
from load_balancer.health import HealthChecker
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.observability import ProxyObserver
from load_balancer.proxy import ProxyHTTPServer, create_proxy_server
from load_balancer.response import ResponseRelay
from load_balancer.routing import create_pool
from load_balancer.upstream import UpstreamTransport


@dataclass(frozen=True, slots=True)
class LoadBalancerApplication:
    """Fully wired runtime components owned by one process."""

    server: ProxyHTTPServer
    health_checker: HealthChecker
    control_plane: ControlPlaneService
    metrics: LoadBalancerMetrics


def build_application(settings: Settings) -> LoadBalancerApplication:
    """Compose runtime dependencies from validated settings."""

    pool = create_pool(list(settings.backends), settings.strategy)
    metrics = LoadBalancerMetrics()
    control_plane = ControlPlaneService(pool)
    observer = ProxyObserver(metrics)
    upstream_transport = UpstreamTransport(
        connect_timeout=settings.upstream_connect_timeout,
        response_timeout=settings.upstream_response_timeout,
    )
    response_relay = ResponseRelay(settings.max_response_body_bytes)
    health_checker = HealthChecker(
        pool,
        path=settings.health_path,
        interval=settings.health_interval,
        timeout=settings.health_timeout,
        failure_threshold=settings.health_failure_threshold,
        success_threshold=settings.health_success_threshold,
        metrics=metrics,
    )
    server = create_proxy_server(
        (settings.listen_host, settings.listen_port),
        pool,
        upstream_connect_timeout=settings.upstream_connect_timeout,
        upstream_response_timeout=settings.upstream_response_timeout,
        max_retries=settings.max_retries,
        max_request_body_bytes=settings.max_request_body_bytes,
        max_response_body_bytes=settings.max_response_body_bytes,
        metrics=metrics,
        control_plane=control_plane,
        observer=observer,
        upstream_transport=upstream_transport,
        response_relay=response_relay,
    )
    return LoadBalancerApplication(
        server,
        health_checker,
        control_plane,
        metrics,
    )
