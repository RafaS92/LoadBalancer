"""Identifiable HTTP backend used by the local load-balancer demonstration."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from typing import Sequence
from urllib.parse import urlsplit

from load_balancer.lifecycle import run_until_shutdown
from load_balancer.server import GracefulThreadingHTTPServer
from load_balancer.validation import port_argument, positive_integer_argument

DEFAULT_MAX_BODY_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class DemoBackendSettings:
    """Validated settings for one demo backend instance."""

    name: str
    host: str
    port: int
    max_body_bytes: int


def non_empty_name(value: str) -> str:
    """Return a normalized non-empty backend name."""

    name = value.strip()
    if not name:
        raise argparse.ArgumentTypeError("backend name must not be empty")
    return name


def parse_demo_settings(
    arguments: Sequence[str] | None = None,
) -> DemoBackendSettings:
    """Parse CLI arguments and environment defaults for one demo backend."""

    parser = argparse.ArgumentParser(description="Run an identifiable demo backend")
    parser.add_argument(
        "--name",
        type=non_empty_name,
        default=os.environ.get("BACKEND_NAME", "backend-a"),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("BACKEND_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=port_argument,
        default=os.environ.get("BACKEND_PORT", "9001"),
    )
    parser.add_argument(
        "--max-body-bytes",
        type=positive_integer_argument,
        default=os.environ.get(
            "BACKEND_MAX_BODY_BYTES",
            str(DEFAULT_MAX_BODY_BYTES),
        ),
    )
    parsed = parser.parse_args(arguments)
    return DemoBackendSettings(
        name=parsed.name,
        host=parsed.host,
        port=parsed.port,
        max_body_bytes=parsed.max_body_bytes,
    )


class DemoBackendServer(GracefulThreadingHTTPServer):
    """Demo server that waits for active request threads when closing."""


class DemoBackendHandler(BaseHTTPRequestHandler):
    """Return health and request identity as small JSON documents."""

    protocol_version = "HTTP/1.1"
    backend_name: str
    max_body_bytes: int

    def do_GET(self) -> None:
        """Return health or request identity."""

        if urlsplit(self.path).path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "backend": self.backend_name,
                },
            )
            return
        self._send_identity("GET")

    def do_POST(self) -> None:
        """Echo one bounded POST body with request identity."""

        body = self._read_body()
        if body is not None:
            self._send_identity("POST", body)

    def do_DELETE(self) -> None:
        """Echo one bounded DELETE body with request identity."""

        body = self._read_body()
        if body is not None:
            self._send_identity("DELETE", body)

    def _read_body(self) -> bytes | None:
        """Read a valid request body within the demo service's memory limit."""

        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError:
            self.close_connection = True
            self._send_json(400, {"error": "invalid_content_length"})
            return None
        if content_length < 0:
            self.close_connection = True
            self._send_json(400, {"error": "invalid_content_length"})
            return None
        if content_length > self.max_body_bytes:
            self.close_connection = True
            self._send_json(413, {"error": "request_body_too_large"})
            return None
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self.close_connection = True
            return None
        return body

    def _send_identity(self, method: str, body: bytes | None = None) -> None:
        """Describe the backend and trusted proxy context for one request."""

        payload: dict[str, str | None] = {
            "backend": self.backend_name,
            "method": method,
            "path": self.path,
            "request_id": self.headers.get("X-Request-Id"),
            "forwarded_for": self.headers.get("X-Forwarded-For"),
            "forwarded_host": self.headers.get("X-Forwarded-Host"),
            "forwarded_proto": self.headers.get("X-Forwarded-Proto"),
        }
        if body is not None:
            payload["body"] = body.decode("utf-8", errors="replace")
        self._send_json(200, payload)

    def _send_json(self, status: int, payload: object) -> None:
        """Send one compact JSON response."""

        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base server's unstructured access log."""


def create_demo_backend_server(
    address: tuple[str, int],
    name: str,
    *,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> DemoBackendServer:
    """Create one configured demo backend server."""

    normalized_name = non_empty_name(name)
    if max_body_bytes <= 0:
        raise ValueError("max body bytes must be positive")
    handler_class = type(
        "ConfiguredDemoBackendHandler",
        (DemoBackendHandler,),
        {
            "backend_name": normalized_name,
            "max_body_bytes": max_body_bytes,
        },
    )
    return DemoBackendServer(address, handler_class)


def main() -> None:
    """Run one demo backend until interrupted."""

    settings = parse_demo_settings()
    server = create_demo_backend_server(
        (settings.host, settings.port),
        settings.name,
        max_body_bytes=settings.max_body_bytes,
    )
    host, port = server.server_address
    print(f"{settings.name} listening on http://{host}:{port}")
    run_until_shutdown(server, thread_name=f"{settings.name}-server")


if __name__ == "__main__":
    main()
