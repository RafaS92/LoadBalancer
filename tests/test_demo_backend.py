import json
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from threading import Thread
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from load_balancer.demo_backend import (
    DEFAULT_MAX_BODY_BYTES,
    create_demo_backend_server,
    parse_demo_settings,
)
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


def server_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"


def test_uses_local_demo_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (
        "BACKEND_NAME",
        "BACKEND_HOST",
        "BACKEND_PORT",
        "BACKEND_MAX_BODY_BYTES",
    ):
        monkeypatch.delenv(variable, raising=False)
    settings = parse_demo_settings([])

    assert settings.name == "backend-a"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9001
    assert settings.max_body_bytes == DEFAULT_MAX_BODY_BYTES


def test_accepts_custom_demo_settings() -> None:
    settings = parse_demo_settings(
        [
            "--name",
            "backend-c",
            "--host",
            "0.0.0.0",
            "--port",
            "9003",
            "--max-body-bytes",
            "2048",
        ]
    )

    assert settings.name == "backend-c"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9003
    assert settings.max_body_bytes == 2048


def test_accepts_environment_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_NAME", "backend-b")
    monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("BACKEND_PORT", "9002")
    monkeypatch.setenv("BACKEND_MAX_BODY_BYTES", "4096")

    settings = parse_demo_settings([])

    assert settings.name == "backend-b"
    assert settings.host == "0.0.0.0"
    assert settings.port == 9002
    assert settings.max_body_bytes == 4096


@pytest.mark.parametrize("arguments", [["--name", " "], ["--port", "70000"]])
def test_rejects_invalid_demo_settings(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_demo_settings(arguments)


def test_health_endpoint_identifies_backend() -> None:
    server = create_demo_backend_server(("127.0.0.1", 0), "backend-b")

    with running_server(server):
        with urlopen(f"{server_url(server)}/health") as response:
            payload = json.load(response)

    assert response.status == 200
    assert response.headers.get_content_type() == "application/json"
    assert payload == {"status": "ok", "backend": "backend-b"}


def test_echoes_proxy_identity_and_request_body() -> None:
    server = create_demo_backend_server(("127.0.0.1", 0), "backend-c")
    request = Request(
        f"{server_url(server)}/orders?source=demo",
        data=b'{"item":"book"}',
        headers={
            "X-Request-Id": "request-123",
            "X-Forwarded-For": "192.0.2.10",
            "X-Forwarded-Host": "api.example",
            "X-Forwarded-Proto": "http",
        },
        method="POST",
    )

    with running_server(server):
        with urlopen(request) as response:
            payload = json.load(response)

    assert payload == {
        "backend": "backend-c",
        "method": "POST",
        "path": "/orders?source=demo",
        "request_id": "request-123",
        "forwarded_for": "192.0.2.10",
        "forwarded_host": "api.example",
        "forwarded_proto": "http",
        "body": '{"item":"book"}',
    }


def test_rejects_oversized_demo_request_body() -> None:
    server = create_demo_backend_server(
        ("127.0.0.1", 0),
        "backend-a",
        max_body_bytes=4,
    )
    request = Request(
        f"{server_url(server)}/orders",
        data=b"12345",
        method="POST",
    )

    with running_server(server):
        with pytest.raises(HTTPError) as raised:
            urlopen(request)

    assert raised.value.code == 413


def test_demo_server_waits_for_active_threads() -> None:
    server = create_demo_backend_server(
        ("127.0.0.1", 0),
        "backend-a",
    )

    assert server.daemon_threads is False


def test_demo_backends_are_identifiable_through_proxy() -> None:
    backend_a = create_demo_backend_server(("127.0.0.1", 0), "backend-a")
    backend_b = create_demo_backend_server(("127.0.0.1", 0), "backend-b")

    def configured_backend(server: ThreadingHTTPServer, name: str) -> Backend:
        host, port = server.server_address
        return Backend(name, f"http://{host}:{port}")

    pool = RoundRobinPool(
        [
            configured_backend(backend_a, "backend-a"),
            configured_backend(backend_b, "backend-b"),
        ]
    )
    proxy = create_proxy_server(("127.0.0.1", 0), pool)

    with (
        running_server(backend_a),
        running_server(backend_b),
        running_server(proxy),
    ):
        selected = []
        for _ in range(2):
            with urlopen(f"{server_url(proxy)}/demo") as response:
                selected.append(json.load(response)["backend"])

    assert selected == ["backend-a", "backend-b"]
