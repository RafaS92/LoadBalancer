import json
import logging
from threading import Event

import httpx
import pytest

from load_balancer.health import HealthChecker
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.routing import Backend, RoundRobinPool

BACKEND = Backend("backend-a", "http://backend-a:9001")


def test_removes_failed_backend_and_restores_it_after_recovery() -> None:
    state = {"status": 503}
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(state["status"])

    pool = RoundRobinPool([BACKEND])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        checker = HealthChecker(pool, client=client)
        checker.check_once()
        assert pool.choose() == BACKEND
        checker.check_once()
        assert pool.choose() is None

        state["status"] = 200
        checker.check_once()
        assert pool.choose() is None
        checker.check_once()
        assert pool.choose() == BACKEND

    assert paths == ["/health", "/health", "/health", "/health"]


def test_success_between_failures_resets_failure_streak() -> None:
    responses = iter([503, 200, 503, 503])

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(responses))

    pool = RoundRobinPool([BACKEND])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        checker = HealthChecker(pool, client=client)
        checker.check_once()
        checker.check_once()
        checker.check_once()
        assert pool.choose() == BACKEND

        checker.check_once()
        assert pool.choose() is None


def test_background_checker_runs_immediately() -> None:
    request_seen = Event()

    def respond(request: httpx.Request) -> httpx.Response:
        request_seen.set()
        return httpx.Response(503)

    pool = RoundRobinPool([BACKEND])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        checker = HealthChecker(
            pool,
            interval=60,
            failure_threshold=1,
            client=client,
        )
        checker.start()
        assert request_seen.wait(timeout=1)
        checker.stop()

    assert pool.choose() is None


def test_network_error_marks_backend_unhealthy() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    pool = RoundRobinPool([BACKEND])
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        checker = HealthChecker(pool, failure_threshold=1, client=client)
        checker.check_once()

    assert pool.choose() is None


def test_health_transitions_emit_logs_and_prometheus_metrics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    state = {"status": 503}

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(state["status"])

    pool = RoundRobinPool([BACKEND])
    metrics = LoadBalancerMetrics()
    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        caplog.at_level(logging.INFO, logger="load_balancer.health"),
    ):
        checker = HealthChecker(
            pool,
            failure_threshold=1,
            success_threshold=1,
            metrics=metrics,
            client=client,
        )
        checker.check_once()
        state["status"] = 200
        checker.check_once()

    events = [json.loads(record.message) for record in caplog.records]
    assert events == [
        {
            "event": "backend_health_changed",
            "backend": "backend-a",
            "healthy": False,
            "reason": "failure_threshold_reached",
            "threshold": 1,
        },
        {
            "event": "backend_health_changed",
            "backend": "backend-a",
            "healthy": True,
            "reason": "success_threshold_reached",
            "threshold": 1,
        },
    ]
    rendered = metrics.render().decode()
    assert 'load_balancer_backend_healthy{backend="backend-a"} 1.0' in rendered
    assert (
        'load_balancer_backend_health_transitions_total{backend="backend-a",'
        'state="unhealthy"} 1.0'
    ) in rendered
    assert (
        'load_balancer_backend_health_transitions_total{backend="backend-a",'
        'state="healthy"} 1.0'
    ) in rendered
