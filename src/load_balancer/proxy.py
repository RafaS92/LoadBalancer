"""Minimal HTTP reverse-proxy server."""

from __future__ import annotations

import json
import logging
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from urllib.parse import unquote, urlsplit

from prometheus_client import CONTENT_TYPE_LATEST

from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.routing import Backend, BackendPool

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
METRICS_PATH = "/metrics"
REQUEST_LOGGER = logging.getLogger("load_balancer.requests")
ADMIN_LOGGER = logging.getLogger("load_balancer.admin")
RETRYABLE_METHODS = {"GET"}
RETRYABLE_OUTCOMES = {"backend_connect_timeout", "backend_connection_failed"}


class UpstreamFailure(Exception):
    """Carry a safe operational outcome from upstream communication."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


class ProxyRequestHandler(BaseHTTPRequestHandler):
    """Forward supported HTTP requests to backends selected by a shared pool."""

    protocol_version = "HTTP/1.1"
    pool: BackendPool
    metrics: LoadBalancerMetrics
    upstream_connect_timeout = 2.0
    upstream_response_timeout = 2.0
    max_retries = 1

    def do_GET(self) -> None:
        """Forward one GET request or return a controlled gateway error."""

        if urlsplit(self.path).path == ADMIN_BACKENDS_PATH:
            self._send_backend_snapshot()
            return
        if urlsplit(self.path).path == METRICS_PATH:
            self._send_body(
                200,
                self.metrics.render(),
                content_type=CONTENT_TYPE_LATEST,
            )
            return
        self._proxy_request("GET")

    def do_POST(self) -> None:
        """Read and forward one POST request body."""

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
        backend_action = self._parse_backend_action()
        if backend_action is not None:
            name, action = backend_action
            self._apply_backend_action(name, action)
            return

        if urlsplit(self.path).path in {ADMIN_BACKENDS_PATH, METRICS_PATH}:
            self._send_body(405, b"Internal endpoint is read-only\n")
            return

        self._proxy_request("POST", body)

    def _proxy_request(self, method: str, body: bytes | None = None) -> None:
        """Select a backend and relay one supported HTTP request."""

        started_at = perf_counter()
        attempted_backends: set[str] = set()
        last_failure: UpstreamFailure | None = None
        failed_backend: Backend | None = None

        for attempt in range(self.max_retries + 1):
            backend = self.pool.acquire(exclude=attempted_backends)
            if backend is None:
                if last_failure is None:
                    self._send_body(503, b"No healthy backends available\n")
                    self._record_completion(
                        method, 503, None, "no_healthy_backend", started_at
                    )
                else:
                    self._send_body(502, b"Selected backend could not be reached\n")
                    self._record_completion(
                        method,
                        502,
                        failed_backend,
                        last_failure.outcome,
                        started_at,
                    )
                return

            if last_failure is not None and failed_backend is not None:
                self.metrics.record_retry(
                    method,
                    last_failure.outcome,
                    failed_backend.name,
                )
            attempted_backends.add(backend.name)
            try:
                try:
                    status, reason, headers, response_body = self._forward(
                        method, backend, body
                    )
                except UpstreamFailure as failure:
                    can_retry = (
                        method in RETRYABLE_METHODS
                        and failure.outcome in RETRYABLE_OUTCOMES
                        and attempt < self.max_retries
                    )
                    if can_retry:
                        last_failure = failure
                        failed_backend = backend
                        continue

                    self._send_body(502, b"Selected backend could not be reached\n")
                    self._record_completion(
                        method,
                        502,
                        backend,
                        failure.outcome,
                        started_at,
                    )
                    return

                self.send_response(status, reason)
                for name, value in headers:
                    lowered = name.lower()
                    if (
                        lowered not in HOP_BY_HOP_HEADERS
                        and lowered != "content-length"
                    ):
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
                outcome = "completed_after_retry" if attempt > 0 else "completed"
                self._record_completion(
                    method,
                    status,
                    backend,
                    outcome,
                    started_at,
                )
                return
            finally:
                self.pool.release(backend.name)

    def _forward(
        self, method: str, backend: Backend, body: bytes | None
    ) -> tuple[int, str, list[tuple[str, str]], bytes]:
        """Send the current request to one backend."""

        target = urlsplit(backend.url)
        if target.scheme != "http" or target.hostname is None:
            raise ValueError(f"unsupported backend URL: {backend.url}")

        connection = HTTPConnection(
            target.hostname,
            target.port or 80,
            timeout=self.upstream_connect_timeout,
        )
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS
            and name.lower() not in {"host", "content-length"}
        }
        headers["Host"] = target.netloc

        try:
            try:
                connection.connect()
            except TimeoutError as error:
                raise UpstreamFailure("backend_connect_timeout") from error
            except (OSError, HTTPException) as error:
                raise UpstreamFailure("backend_connection_failed") from error

            if connection.sock is None:
                raise UpstreamFailure("backend_connection_failed")
            connection.sock.settimeout(self.upstream_response_timeout)
            try:
                connection.request(method, self.path, body=body, headers=headers)
                response = connection.getresponse()
                body = response.read()
                return response.status, response.reason, response.getheaders(), body
            except TimeoutError as error:
                raise UpstreamFailure("backend_response_timeout") from error
            except (OSError, HTTPException) as error:
                raise UpstreamFailure("backend_response_failed") from error
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
                    "enabled": status.enabled,
                    "draining": status.draining,
                    "drained": status.draining and status.active_requests == 0,
                    "active_requests": status.active_requests,
                }
                for status in self.pool.snapshot()
            ]
        ).encode()
        self._send_body(200, body, content_type="application/json")

    def _parse_backend_action(self) -> tuple[str, str] | None:
        """Parse an enable, disable, or drain backend action."""

        parts = urlsplit(self.path).path.split("/")
        if (
            len(parts) != 5
            or parts[:3] != ["", "admin", "backends"]
            or not parts[3]
            or parts[4] not in {"enable", "disable", "drain"}
        ):
            return None
        return unquote(parts[3]), parts[4]

    def _apply_backend_action(self, name: str, action: str) -> None:
        """Apply one operator routing action and return the resulting state."""

        try:
            if action == "drain":
                self.pool.begin_drain(name)
            else:
                self.pool.set_enabled(name, enabled=action == "enable")
        except KeyError:
            self._send_body(404, b"Unknown backend\n")
            return

        status = next(
            status for status in self.pool.snapshot() if status.backend.name == name
        )
        body = json.dumps(
            {
                "name": status.backend.name,
                "healthy": status.healthy,
                "enabled": status.enabled,
                "draining": status.draining,
                "drained": status.draining and status.active_requests == 0,
                "active_requests": status.active_requests,
            }
        ).encode()
        self._send_body(200, body, content_type="application/json")
        ADMIN_LOGGER.info(
            json.dumps(
                {
                    "event": "backend_operator_state_changed",
                    "backend": name,
                    "action": action,
                    "enabled": status.enabled,
                    "draining": status.draining,
                },
                separators=(",", ":"),
            )
        )

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

    def _record_completion(
        self,
        method: str,
        status: int,
        backend: Backend | None,
        outcome: str,
        started_at: float,
    ) -> None:
        """Record metrics and write one log for a completed proxy request."""

        duration_seconds = perf_counter() - started_at
        backend_name = backend.name if backend is not None else None
        self.metrics.record(
            method=method,
            status=status,
            outcome=outcome,
            backend=backend_name,
            duration_seconds=duration_seconds,
        )
        REQUEST_LOGGER.info(
            json.dumps(
                {
                    "event": "proxy_request_completed",
                    "method": method,
                    "path": self.path,
                    "status": status,
                    "backend": backend_name,
                    "outcome": outcome,
                    "duration_ms": round(duration_seconds * 1000, 3),
                },
                separators=(",", ":"),
            )
        )

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base handler's duplicate unstructured access log."""


def create_proxy_server(
    address: tuple[str, int],
    pool: BackendPool,
    *,
    upstream_connect_timeout: float = 2.0,
    upstream_response_timeout: float = 2.0,
    max_retries: int = 1,
    metrics: LoadBalancerMetrics | None = None,
) -> ThreadingHTTPServer:
    """Create a threaded server whose handlers share one backend pool."""

    handler_class = type(
        "ConfiguredProxyRequestHandler",
        (ProxyRequestHandler,),
        {
            "pool": pool,
            "metrics": metrics or LoadBalancerMetrics(),
            "upstream_connect_timeout": upstream_connect_timeout,
            "upstream_response_timeout": upstream_response_timeout,
            "max_retries": max_retries,
        },
    )
    return ThreadingHTTPServer(address, handler_class)
