import json
import logging
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from load_balancer.proxy import create_proxy_server
from load_balancer.routing import Backend, RoundRobinPool


@contextmanager
def running_server(server: ThreadingHTTPServer) -> Iterator[None]:
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def backend_server(name: str) -> ThreadingHTTPServer:
    class IdentifiableBackend(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps({"backend": name, "path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Backend", name)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(content_length)
            body = json.dumps(
                {
                    "backend": name,
                    "path": self.path,
                    "content_type": self.headers.get("Content-Type"),
                    "body": request_body.decode(),
                }
            ).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), IdentifiableBackend)


def backend_for(server: ThreadingHTTPServer, name: str) -> Backend:
    host, port = server.server_address
    return Backend(name, f"http://{host}:{port}")


def proxy_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"


def test_forwards_path_and_query_and_preserves_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(upstream),
        running_server(proxy),
    ):
        with urlopen(f"{proxy_url(proxy)}/items?limit=5") as response:
            payload = json.load(response)

            assert response.status == 200
            assert response.headers["X-Backend"] == "backend-a"
            assert payload == {"backend": "backend-a", "path": "/items?limit=5"}

    event = json.loads(caplog.records[-1].message)
    assert event == {
        "event": "proxy_request_completed",
        "method": "GET",
        "path": "/items?limit=5",
        "status": 200,
        "backend": "backend-a",
        "outcome": "completed",
        "duration_ms": event["duration_ms"],
    }
    assert event["duration_ms"] >= 0


def test_routes_successive_requests_round_robin() -> None:
    upstream_a = backend_server("backend-a")
    upstream_b = backend_server("backend-b")
    pool = RoundRobinPool(
        [
            backend_for(upstream_a, "backend-a"),
            backend_for(upstream_b, "backend-b"),
        ]
    )
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        running_server(upstream_a),
        running_server(upstream_b),
        running_server(proxy),
    ):
        with urlopen(f"{proxy_url(proxy)}/admin/backends"):
            pass

        selected = []
        for _ in range(4):
            with urlopen(f"{proxy_url(proxy)}/") as response:
                selected.append(json.load(response)["backend"])

    assert selected == ["backend-a", "backend-b", "backend-a", "backend-b"]


def test_admin_endpoint_returns_backend_snapshot() -> None:
    backends = [
        Backend("backend-a", "http://127.0.0.1:9001"),
        Backend("backend-b", "http://127.0.0.1:9002"),
    ]
    pool = RoundRobinPool(backends)
    pool.set_health("backend-b", healthy=False)
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with running_server(proxy):
        with urlopen(f"{proxy_url(proxy)}/admin/backends") as response:
            payload = json.load(response)

            assert response.status == 200
            assert response.headers.get_content_type() == "application/json"
            assert payload == [
                {
                    "name": "backend-a",
                    "url": "http://127.0.0.1:9001",
                    "healthy": True,
                    "active_requests": 0,
                },
                {
                    "name": "backend-b",
                    "url": "http://127.0.0.1:9002",
                    "healthy": False,
                    "active_requests": 0,
                },
            ]


def test_admin_snapshot_shows_active_request_until_it_completes() -> None:
    request_started = Event()
    allow_response = Event()

    class BlockingBackend(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request_started.set()
            allow_response.wait(timeout=2)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), BlockingBackend)
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    errors: list[Exception] = []

    def send_request() -> None:
        try:
            with urlopen(f"{proxy_url(proxy)}/slow"):
                pass
        except Exception as error:
            errors.append(error)

    with running_server(upstream), running_server(proxy):
        request_thread = Thread(target=send_request)
        request_thread.start()
        try:
            assert request_started.wait(timeout=1)
            with urlopen(f"{proxy_url(proxy)}/admin/backends") as response:
                assert json.load(response)[0]["active_requests"] == 1
        finally:
            allow_response.set()
            request_thread.join()

        with urlopen(f"{proxy_url(proxy)}/admin/backends") as response:
            assert json.load(response)[0]["active_requests"] == 0

    assert errors == []


def test_admin_endpoint_rejects_post() -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:9001")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    request = Request(
        f"{proxy_url(proxy)}/admin/backends",
        data=b"{}",
        method="POST",
    )

    with running_server(proxy):
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 405
            assert error.read() == b"Internal endpoint is read-only\n"
        else:
            raise AssertionError("expected the administration endpoint to reject POST")


def test_metrics_endpoint_exposes_request_count_and_latency() -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with running_server(upstream), running_server(proxy):
        with urlopen(f"{proxy_url(proxy)}/items"):
            pass
        with urlopen(f"{proxy_url(proxy)}/metrics") as response:
            metrics = response.read().decode()

            assert response.status == 200
            assert response.headers.get_content_type() == "text/plain"

    request_lines = [
        line
        for line in metrics.splitlines()
        if line.startswith("load_balancer_proxy_requests_total{")
    ]
    assert len(request_lines) == 1
    assert 'backend="backend-a"' in request_lines[0]
    assert 'method="GET"' in request_lines[0]
    assert 'outcome="completed"' in request_lines[0]
    assert 'status="200"' in request_lines[0]
    assert request_lines[0].endswith(" 1.0")
    assert "load_balancer_proxy_request_duration_seconds_count" in metrics


def test_forwards_post_body_and_content_type() -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    request = Request(
        f"{proxy_url(proxy)}/orders",
        data=b'{"item":"book"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with running_server(upstream), running_server(proxy):
        with urlopen(request) as response:
            payload = json.load(response)

            assert response.status == 201
            assert payload == {
                "backend": "backend-a",
                "path": "/orders",
                "content_type": "application/json",
                "body": '{"item":"book"}',
            }


def test_returns_503_when_no_backend_is_healthy(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = Backend("backend-a", "http://127.0.0.1:1")
    pool = RoundRobinPool([backend])
    pool.set_health("backend-a", healthy=False)
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(proxy),
    ):
        try:
            urlopen(f"{proxy_url(proxy)}/")
        except HTTPError as error:
            assert error.code == 503
            assert error.read() == b"No healthy backends available\n"
        else:
            raise AssertionError("expected the proxy to return 503")

    event = json.loads(caplog.records[-1].message)
    assert event["status"] == 503
    assert event["backend"] is None
    assert event["outcome"] == "no_healthy_backend"
