from load_balancer.control_plane import ControlPlaneService
from load_balancer.dashboard import DashboardReadModel, DashboardService
from load_balancer.routing import Backend, RoundRobinPool


def test_combines_backend_state_and_traffic_aggregates() -> None:
    backend_a = Backend("backend-a", "http://127.0.0.1:9001")
    backend_b = Backend("backend-b", "http://127.0.0.1:9002")
    pool = RoundRobinPool([backend_a, backend_b])
    pool.set_health("backend-b", healthy=False)
    traffic = DashboardReadModel()
    traffic.record_completion(
        method="GET",
        path="/items",
        status=200,
        backend=backend_a,
        outcome="completed",
        duration_seconds=0.02,
        request_id="request-1",
    )
    traffic.record_completion(
        method="GET",
        path="/failed",
        status=502,
        backend=backend_a,
        outcome="backend_response_failed",
        duration_seconds=0.08,
        request_id="request-2",
    )
    traffic.record_retry(backend_a)

    snapshot = DashboardService(ControlPlaneService(pool), traffic).snapshot()

    assert snapshot["summary"] == {
        "backends_total": 2,
        "healthy_backends": 1,
        "available_backends": 1,
        "active_requests": 0,
        "requests_total": 2,
        "failures_total": 1,
        "retries_total": 1,
        "average_latency_ms": 50.0,
    }
    backends = snapshot["backends"]
    assert isinstance(backends, list)
    assert backends[0] == {
        "name": "backend-a",
        "url": "http://127.0.0.1:9001",
        "healthy": True,
        "enabled": True,
        "draining": False,
        "drained": False,
        "active_requests": 0,
        "requests_total": 2,
        "failures_total": 1,
        "retries_total": 1,
        "average_latency_ms": 50.0,
    }
    assert backends[1]["healthy"] is False
    recent_requests = snapshot["recent_requests"]
    assert isinstance(recent_requests, list)
    assert [request["request_id"] for request in recent_requests] == [
        "request-2",
        "request-1",
    ]


def test_recent_request_history_is_bounded() -> None:
    traffic = DashboardReadModel(recent_request_limit=2)
    backend = Backend("backend-a", "http://127.0.0.1:9001")

    for index in range(3):
        traffic.record_completion(
            method="GET",
            path=f"/items/{index}",
            status=200,
            backend=backend,
            outcome="completed",
            duration_seconds=0.01,
            request_id=f"request-{index}",
        )

    recent_requests = traffic.snapshot()["recent_requests"]
    assert isinstance(recent_requests, list)
    assert [request["request_id"] for request in recent_requests] == [
        "request-2",
        "request-1",
    ]
