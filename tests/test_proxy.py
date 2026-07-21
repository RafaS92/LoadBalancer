import json
import logging
import socket
from contextlib import contextmanager
from http.client import HTTPConnection, RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID

import pytest

import load_balancer.proxy as proxy_module
from load_balancer.proxy import ProxyRequestHandler, create_proxy_server
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

        do_DELETE = do_POST

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
            request_id = response.headers["X-Request-Id"]
            assert payload == {"backend": "backend-a", "path": "/items?limit=5"}

    event = json.loads(caplog.records[-1].message)
    assert event == {
        "event": "proxy_request_completed",
        "method": "GET",
        "path": "/items?limit=5",
        "status": 200,
        "backend": "backend-a",
        "outcome": "completed",
        "request_id": request_id,
        "duration_ms": event["duration_ms"],
    }
    assert UUID(request_id)
    assert event["duration_ms"] >= 0


def test_proxy_server_waits_for_active_request_threads() -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    assert proxy.daemon_threads is False
    assert proxy.block_on_close is True


def test_forwards_trusted_client_identity_headers() -> None:
    class HeaderBackend(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = json.dumps(
                {
                    "host": self.headers.get("Host"),
                    "forwarded_for": self.headers.get("X-Forwarded-For"),
                    "forwarded_host": self.headers.get("X-Forwarded-Host"),
                    "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
                    "request_id": self.headers.get("X-Request-Id"),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), HeaderBackend)
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    request = Request(
        f"{proxy_url(proxy)}/identity",
        headers={
            "X-Forwarded-For": "203.0.113.10",
            "X-Forwarded-Host": "spoofed.example",
            "X-Forwarded-Proto": "https",
            "X-Request-Id": "request-123",
        },
    )

    with running_server(upstream), running_server(proxy):
        with urlopen(request) as response:
            payload = json.load(response)
            returned_request_id = response.headers["X-Request-Id"]

        invalid_request = Request(
            f"{proxy_url(proxy)}/identity",
            headers={"X-Request-Id": "not a valid request id"},
        )
        with urlopen(invalid_request) as response:
            invalid_payload = json.load(response)
            generated_request_id = response.headers["X-Request-Id"]

    upstream_host, upstream_port = upstream.server_address
    proxy_host, proxy_port = proxy.server_address
    assert payload == {
        "host": f"{upstream_host}:{upstream_port}",
        "forwarded_for": "127.0.0.1",
        "forwarded_host": f"{proxy_host}:{proxy_port}",
        "forwarded_proto": "http",
        "request_id": "request-123",
    }
    assert returned_request_id == "request-123"
    assert invalid_payload["request_id"] == generated_request_id
    assert generated_request_id != "not a valid request id"
    assert UUID(generated_request_id)


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
                    "enabled": True,
                    "draining": False,
                    "drained": False,
                    "active_requests": 0,
                },
                {
                    "name": "backend-b",
                    "url": "http://127.0.0.1:9002",
                    "healthy": False,
                    "enabled": True,
                    "draining": False,
                    "drained": False,
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
            drain_request = Request(
                f"{proxy_url(proxy)}/admin/backends/backend-a/drain",
                data=b"",
                method="POST",
            )
            with urlopen(drain_request) as response:
                draining = json.load(response)
                assert draining["active_requests"] == 1
                assert draining["draining"] is True
                assert draining["drained"] is False
        finally:
            allow_response.set()
            request_thread.join()

        with urlopen(f"{proxy_url(proxy)}/admin/backends") as response:
            drained = json.load(response)[0]
            assert drained["active_requests"] == 0
            assert drained["draining"] is True
            assert drained["drained"] is True

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


def test_admin_can_disable_and_enable_backend() -> None:
    upstream_a = backend_server("backend-a")
    upstream_b = backend_server("backend-b")
    pool = RoundRobinPool(
        [
            backend_for(upstream_a, "backend-a"),
            backend_for(upstream_b, "backend-b"),
        ]
    )
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    def change_state(action: str) -> dict[str, object]:
        request = Request(
            f"{proxy_url(proxy)}/admin/backends/backend-a/{action}",
            data=b"",
            method="POST",
        )
        with urlopen(request) as response:
            return json.load(response)

    with (
        running_server(upstream_a),
        running_server(upstream_b),
        running_server(proxy),
    ):
        assert change_state("disable")["enabled"] is False
        with urlopen(f"{proxy_url(proxy)}/") as response:
            assert json.load(response)["backend"] == "backend-b"

        pool.set_health("backend-a", healthy=False)
        pool.set_health("backend-a", healthy=True)
        with urlopen(f"{proxy_url(proxy)}/") as response:
            assert json.load(response)["backend"] == "backend-b"

        assert change_state("enable")["enabled"] is True
        with urlopen(f"{proxy_url(proxy)}/") as response:
            assert json.load(response)["backend"] == "backend-a"


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


def test_response_timeout_returns_502_and_releases_backend(
    caplog: pytest.LogCaptureFixture,
) -> None:
    allow_response = Event()

    class SlowBackend(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            allow_response.wait(timeout=1)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), SlowBackend)
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(
        ("127.0.0.1", 0),
        pool,
        upstream_response_timeout=0.05,
    )

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(upstream),
        running_server(proxy),
    ):
        try:
            urlopen(f"{proxy_url(proxy)}/slow")
        except HTTPError as error:
            assert error.code == 502
            assert error.read() == b"Selected backend could not be reached\n"
        else:
            raise AssertionError("expected a slow backend to return 502")
        finally:
            allow_response.set()

    assert pool.snapshot()[0].active_requests == 0
    assert json.loads(caplog.records[-1].message)["outcome"] == (
        "backend_response_timeout"
    )


def test_client_disconnect_releases_backend_and_records_outcome(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])

    def simulate_disconnect(
        self: ProxyRequestHandler,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        body: bytes,
        request_id: str,
    ) -> bool:
        del status, reason, headers, body, request_id
        self.close_connection = True
        return False

    monkeypatch.setattr(
        ProxyRequestHandler,
        "_send_upstream_response",
        simulate_disconnect,
    )
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(upstream),
        running_server(proxy),
    ):
        with pytest.raises(RemoteDisconnected):
            urlopen(f"{proxy_url(proxy)}/disconnect")

    assert pool.snapshot()[0].active_requests == 0
    event = json.loads(caplog.records[-1].message)
    assert event["status"] == 499
    assert event["backend"] == "backend-a"
    assert event["outcome"] == "client_disconnected"


def test_upstream_response_writer_suppresses_broken_pipe() -> None:
    class DisconnectingWriter:
        def write(self, body: bytes) -> None:
            del body
            raise BrokenPipeError

    class HandlerHarness:
        close_connection = False
        wfile = DisconnectingWriter()

        def send_response(self, status: int, reason: str) -> None:
            del status, reason

        def send_header(self, name: str, value: str) -> None:
            del name, value

        def end_headers(self) -> None:
            pass

    handler = HandlerHarness()
    sent = ProxyRequestHandler._send_upstream_response(
        handler,  # type: ignore[arg-type]
        200,
        "OK",
        [],
        b"response",
        "request-123",
    )

    assert sent is False
    assert handler.close_connection is True


def test_disconnect_during_request_body_does_not_select_backend(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    host, port = proxy.server_address

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(proxy),
        socket.create_connection((host, port)) as client,
    ):
        client.sendall(
            b"POST /orders HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"abc"
        )
        client.shutdown(socket.SHUT_WR)
        assert client.recv(1) == b""

    assert pool.snapshot()[0].active_requests == 0
    event = json.loads(caplog.records[-1].message)
    assert event["status"] == 499
    assert event["backend"] is None
    assert event["outcome"] == "client_disconnected"


def test_connect_timeout_is_classified_in_logs_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class TimedOutConnection:
        sock = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def connect(self) -> None:
            raise TimeoutError

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "load_balancer.proxy.HTTPConnection",
        TimedOutConnection,
    )
    pool = RoundRobinPool([Backend("backend-a", "http://backend-a:9001")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(proxy),
    ):
        try:
            urlopen(f"{proxy_url(proxy)}/items")
        except HTTPError as error:
            assert error.code == 502
        else:
            raise AssertionError("expected a connection timeout to return 502")

        with urlopen(f"{proxy_url(proxy)}/metrics") as response:
            metrics = response.read().decode()

    event = json.loads(caplog.records[-1].message)
    assert event["outcome"] == "backend_connect_timeout"
    assert 'outcome="backend_connect_timeout"' in metrics
    assert pool.snapshot()[0].active_requests == 0


def test_get_retries_different_backend_after_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original_connection = proxy_module.HTTPConnection

    class TimedOutConnection:
        sock = None

        def connect(self) -> None:
            raise TimeoutError

        def close(self) -> None:
            pass

    def connection_factory(
        host: str, port: int, *, timeout: float
    ) -> object:
        if host == "failed-backend":
            return TimedOutConnection()
        return original_connection(host, port, timeout=timeout)

    monkeypatch.setattr(proxy_module, "HTTPConnection", connection_factory)
    upstream = backend_server("backend-b")
    pool = RoundRobinPool(
        [
            Backend("backend-a", "http://failed-backend:9001"),
            backend_for(upstream, "backend-b"),
        ]
    )
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(upstream),
        running_server(proxy),
    ):
        with urlopen(f"{proxy_url(proxy)}/retry") as response:
            assert json.load(response)["backend"] == "backend-b"
        with urlopen(f"{proxy_url(proxy)}/metrics") as response:
            metrics = response.read().decode()

    event = json.loads(caplog.records[-1].message)
    assert event["backend"] == "backend-b"
    assert event["outcome"] == "completed_after_retry"
    assert 'failed_backend="backend-a"' in metrics
    assert 'reason="backend_connect_timeout"' in metrics


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_mutating_methods_are_not_retried_after_connect_timeout(
    method: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    original_connection = proxy_module.HTTPConnection

    class TimedOutConnection:
        sock = None

        def connect(self) -> None:
            raise TimeoutError

        def close(self) -> None:
            pass

    def connection_factory(
        host: str, port: int, *, timeout: float
    ) -> object:
        if host == "failed-backend":
            return TimedOutConnection()
        return original_connection(host, port, timeout=timeout)

    monkeypatch.setattr(proxy_module, "HTTPConnection", connection_factory)
    upstream = backend_server("backend-b")
    pool = RoundRobinPool(
        [
            Backend("backend-a", "http://failed-backend:9001"),
            backend_for(upstream, "backend-b"),
        ]
    )
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    request = Request(
        f"{proxy_url(proxy)}/orders",
        data=b'{"item":"book"}',
        headers={"Content-Type": "application/json"},
        method=method,
    )

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(upstream),
        running_server(proxy),
    ):
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 502
        else:
            raise AssertionError(f"expected {method} connection timeout to return 502")

    event = json.loads(caplog.records[-1].message)
    assert event["backend"] == "backend-a"
    assert event["outcome"] == "backend_connect_timeout"


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


def test_rejects_post_body_larger_than_configured_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(
        ("127.0.0.1", 0),
        pool,
        max_request_body_bytes=4,
    )
    request = Request(
        f"{proxy_url(proxy)}/orders",
        data=b"12345",
        method="POST",
    )

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(proxy),
    ):
        with pytest.raises(HTTPError) as raised:
            urlopen(request)

        assert raised.value.code == 413
        assert raised.value.read() == b"Request body exceeds configured limit\n"
        request_id = raised.value.headers["X-Request-Id"]

    assert pool.snapshot()[0].active_requests == 0
    event = json.loads(caplog.records[-1].message)
    assert event["status"] == 413
    assert event["backend"] is None
    assert event["outcome"] == "request_body_too_large"
    assert event["request_id"] == request_id


def test_accepts_post_body_at_configured_limit() -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(
        ("127.0.0.1", 0),
        pool,
        max_request_body_bytes=5,
    )
    request = Request(
        f"{proxy_url(proxy)}/orders",
        data=b"12345",
        method="POST",
    )

    with running_server(upstream), running_server(proxy):
        with urlopen(request) as response:
            payload = json.load(response)
            status = response.status

    assert status == 201
    assert payload["body"] == "12345"


def test_forwards_delete_body() -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    request = Request(
        f"{proxy_url(proxy)}/items/42",
        data=b'{"name":"updated"}',
        headers={"Content-Type": "application/json"},
        method="DELETE",
    )

    with running_server(upstream), running_server(proxy):
        with urlopen(request) as response:
            payload = json.load(response)

    assert response.status == 201
    assert payload == {
        "backend": "backend-a",
        "path": "/items/42",
        "content_type": "application/json",
        "body": '{"name":"updated"}',
    }


def test_delete_cannot_reach_internal_endpoints() -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    request = Request(
        f"{proxy_url(proxy)}/metrics",
        data=b"",
        method="DELETE",
    )

    with running_server(proxy):
        with pytest.raises(HTTPError) as raised:
            urlopen(request)

    assert raised.value.code == 405
    assert pool.snapshot()[0].active_requests == 0


def test_request_body_limit_applies_to_delete() -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(
        ("127.0.0.1", 0),
        pool,
        max_request_body_bytes=4,
    )
    request = Request(
        f"{proxy_url(proxy)}/items/42",
        data=b"12345",
        method="DELETE",
    )

    with running_server(proxy):
        with pytest.raises(HTTPError) as raised:
            urlopen(request)

    assert raised.value.code == 413
    assert pool.snapshot()[0].active_requests == 0


def test_rejects_backend_response_larger_than_configured_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class LargeResponseBackend(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"12345"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), LargeResponseBackend)
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(
        ("127.0.0.1", 0),
        pool,
        max_response_body_bytes=4,
    )

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(upstream),
        running_server(proxy),
    ):
        with pytest.raises(HTTPError) as raised:
            urlopen(f"{proxy_url(proxy)}/large")

        assert raised.value.code == 502
        assert raised.value.read() == b"Selected backend could not be reached\n"

    assert pool.snapshot()[0].active_requests == 0
    event = json.loads(caplog.records[-1].message)
    assert event["status"] == 502
    assert event["backend"] == "backend-a"
    assert event["outcome"] == "backend_response_too_large"


def test_accepts_backend_response_at_configured_limit() -> None:
    class BoundedResponseBackend(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"12345"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), BoundedResponseBackend)
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(
        ("127.0.0.1", 0),
        pool,
        max_response_body_bytes=5,
    )

    with running_server(upstream), running_server(proxy):
        with urlopen(f"{proxy_url(proxy)}/bounded") as response:
            body = response.read()
            status = response.status

    assert status == 200
    assert body == b"12345"


def test_rejects_chunked_request_framing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    host, port = proxy.server_address

    with (
        caplog.at_level(logging.INFO, logger="load_balancer.requests"),
        running_server(proxy),
    ):
        connection = HTTPConnection(host, port)
        try:
            connection.request(
                "POST",
                "/orders",
                body=iter([b"payload"]),
                encode_chunked=True,
            )
            response = connection.getresponse()
            assert response.status == 501
            assert response.read() == b"Transfer-Encoding is not supported\n"
        finally:
            connection.close()

    assert pool.snapshot()[0].active_requests == 0
    event = json.loads(caplog.records[-1].message)
    assert event["outcome"] == "unsupported_transfer_encoding"


def test_rejects_multiple_content_length_headers() -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    host, port = proxy.server_address

    with running_server(proxy):
        connection = HTTPConnection(host, port)
        try:
            connection.putrequest("POST", "/orders")
            connection.putheader("Content-Length", "3")
            connection.putheader("Content-Length", "4")
            connection.endheaders(b"abc")
            response = connection.getresponse()
            assert response.status == 400
            assert (
                response.read()
                == b"Multiple Content-Length headers are not supported\n"
            )
        finally:
            connection.close()

    assert pool.snapshot()[0].active_requests == 0


def test_rejects_get_request_body() -> None:
    pool = RoundRobinPool([Backend("backend-a", "http://127.0.0.1:1")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)
    host, port = proxy.server_address

    with running_server(proxy):
        connection = HTTPConnection(host, port)
        try:
            connection.request("GET", "/items", body=b"payload")
            response = connection.getresponse()
            assert response.status == 400
            assert (
                response.read()
                == b"Request body is not supported for this method\n"
            )
        finally:
            connection.close()

    assert pool.snapshot()[0].active_requests == 0


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
