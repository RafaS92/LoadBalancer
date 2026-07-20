"""Minimal HTTP reverse-proxy server."""

from __future__ import annotations

import http.client
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from urllib.parse import urlsplit

from load_balancer.routing import Backend, RoundRobinPool

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
ADMIN_BACKENDS_PATH = "/admin/backends"
REQUEST_LOGGER = logging.getLogger("load_balancer.requests")


class ProxyRequestHandler(BaseHTTPRequestHandler):
    """Forward supported HTTP requests to backends selected by a shared pool."""

    protocol_version = "HTTP/1.1"
    pool: RoundRobinPool
    upstream_timeout = 2.0

    def do_GET(self) -> None:
        """Forward one GET request or return a controlled gateway error."""

        if urlsplit(self.path).path == ADMIN_BACKENDS_PATH:
            self._send_backend_snapshot()
            return
        self._proxy_request("GET")

    def do_POST(self) -> None:
        """Read and forward one POST request body."""

        if urlsplit(self.path).path == ADMIN_BACKENDS_PATH:
            self._send_body(405, b"Administration endpoint is read-only\n")
            return

        raw_length = self.headers.get("Content-Length", "0")
        try:
            content_length = int(raw_length)
        except ValueError:
            self._send_body(400, b"Invalid Content-Length header\n")
            return

        if content_length < 0:
            self._send_body(400, b"Invalid Content-Length header\n")
            return

        body = self.rfile.read(content_length)
        self._proxy_request("POST", body)

    def _proxy_request(self, method: str, body: bytes | None = None) -> None:
        """Select a backend and relay one supported HTTP request."""

        started_at = perf_counter()
        backend = self.pool.choose()
        if backend is None:
            self._send_body(503, b"No healthy backends available\n")
            self._log_request(method, 503, None, "no_healthy_backend", started_at)
            return

        try:
            status, reason, headers, response_body = self._forward(
                method, backend, body
            )
        except (OSError, http.client.HTTPException):
            self._send_body(502, b"Selected backend could not be reached\n")
            self._log_request(
                method,
                502,
                backend,
                "backend_connection_failed",
                started_at,
            )
            return

        self.send_response(status, reason)
        for name, value in headers:
            lowered = name.lower()
            if lowered not in HOP_BY_HOP_HEADERS and lowered != "content-length":
                self.send_header(name, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)
        self._log_request(method, status, backend, "completed", started_at)

    def _forward(
        self, method: str, backend: Backend, body: bytes | None
    ) -> tuple[int, str, list[tuple[str, str]], bytes]:
        """Send the current request to one backend."""

        target = urlsplit(backend.url)
        if target.scheme != "http" or target.hostname is None:
            raise ValueError(f"unsupported backend URL: {backend.url}")

        connection = http.client.HTTPConnection(
            target.hostname,
            target.port or 80,
            timeout=self.upstream_timeout,
        )
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS
            and name.lower() not in {"host", "content-length"}
        }
        headers["Host"] = target.netloc

        try:
            connection.request(method, self.path, body=body, headers=headers)
            response = connection.getresponse()
            body = response.read()
            return response.status, response.reason, response.getheaders(), body
        finally:
            connection.close()

    def _send_backend_snapshot(self) -> None:
        """Return the current backend state without changing routing."""

        body = json.dumps(
            [
                {
                    "name": status.backend.name,
                    "url": status.backend.url,
                    "healthy": status.healthy,
                }
                for status in self.pool.snapshot()
            ]
        ).encode()
        self._send_body(200, body, content_type="application/json")

    def _send_body(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        """Send a small response with an explicit content type and body length."""

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _log_request(
        self,
        method: str,
        status: int,
        backend: Backend | None,
        outcome: str,
        started_at: float,
    ) -> None:
        """Write one structured event for a completed proxy request."""

        REQUEST_LOGGER.info(
            json.dumps(
                {
                    "event": "proxy_request_completed",
                    "method": method,
                    "path": self.path,
                    "status": status,
                    "backend": backend.name if backend is not None else None,
                    "outcome": outcome,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
                separators=(",", ":"),
            )
        )

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base handler's duplicate unstructured access log."""


def create_proxy_server(
    address: tuple[str, int],
    pool: RoundRobinPool,
    *,
    upstream_timeout: float = 2.0,
) -> ThreadingHTTPServer:
    """Create a threaded server whose handlers share one backend pool."""

    handler_class = type(
        "ConfiguredProxyRequestHandler",
        (ProxyRequestHandler,),
        {"pool": pool, "upstream_timeout": upstream_timeout},
    )
    return ThreadingHTTPServer(address, handler_class)
