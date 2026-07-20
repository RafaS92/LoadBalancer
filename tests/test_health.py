from threading import Event

import httpx

from load_balancer.health import HealthChecker
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
        assert pool.choose() is None

        state["status"] = 200
        checker.check_once()
        assert pool.choose() == BACKEND

    assert paths == ["/health", "/health"]


def test_background_checker_runs_immediately() -> None:
    request_seen = Event()

    def respond(request: httpx.Request) -> httpx.Response:
        request_seen.set()
        return httpx.Response(503)

    pool = RoundRobinPool([BACKEND])
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        checker = HealthChecker(pool, interval=60, client=client)
        checker.start()
        assert request_seen.wait(timeout=1)
        checker.stop()

    assert pool.choose() is None


def test_network_error_marks_backend_unhealthy() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    pool = RoundRobinPool([BACKEND])
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        checker = HealthChecker(pool, client=client)
        checker.check_once()

    assert pool.choose() is None
