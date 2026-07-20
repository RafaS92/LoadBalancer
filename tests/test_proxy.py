import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import urlopen

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

        def log_message(self, format: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", 0), IdentifiableBackend)


def backend_for(server: ThreadingHTTPServer, name: str) -> Backend:
    host, port = server.server_address
    return Backend(name, f"http://{host}:{port}")


def proxy_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"


def test_forwards_path_and_query_and_preserves_response() -> None:
    upstream = backend_server("backend-a")
    pool = RoundRobinPool([backend_for(upstream, "backend-a")])
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with running_server(upstream), running_server(proxy):
        with urlopen(f"{proxy_url(proxy)}/items?limit=5") as response:
            payload = json.load(response)

            assert response.status == 200
            assert response.headers["X-Backend"] == "backend-a"
            assert payload == {"backend": "backend-a", "path": "/items?limit=5"}


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
        selected = []
        for _ in range(4):
            with urlopen(f"{proxy_url(proxy)}/") as response:
                selected.append(json.load(response)["backend"])

    assert selected == ["backend-a", "backend-b", "backend-a", "backend-b"]


def test_returns_503_when_no_backend_is_healthy() -> None:
    backend = Backend("backend-a", "http://127.0.0.1:1")
    pool = RoundRobinPool([backend])
    pool.set_health("backend-a", healthy=False)
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with running_server(proxy):
        try:
            urlopen(f"{proxy_url(proxy)}/")
        except HTTPError as error:
            assert error.code == 503
            assert error.read() == b"No healthy backends available\n"
        else:
            raise AssertionError("expected the proxy to return 503")
