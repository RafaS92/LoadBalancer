"""Minimal HTTP reverse-proxy server."""

from __future__ import annotations

import json
import re
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
from time import perf_counter
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from prometheus_client import CONTENT_TYPE_LATEST

from load_balancer.control_plane import ControlPlaneService
from load_balancer.http_framing import (
    RequestFramingError,
    request_content_length,
)
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.observability import ProxyObserver
from load_balancer.response import ResponseRelay, forwarded_response_headers
from load_balancer.routing import Backend, BackendPool
from load_balancer.server import GracefulThreadingHTTPServer
from load_balancer.upstream import (
    UpstreamFailure,
    UpstreamRequest,
    UpstreamTransport,
)

ADMIN_BACKENDS_PATH = "/admin/backends"
METRICS_PATH = "/metrics"
RETRYABLE_METHODS = {"GET"}
RETRYABLE_OUTCOMES = {"backend_connect_timeout", "backend_connection_failed"}
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class ProxyHTTPServer(GracefulThreadingHTTPServer):
    """Threaded HTTP server that waits for active requests during close."""


class ProxyRequestHandler(BaseHTTPRequestHandler):
    """Forward supported HTTP requests to backends selected by a shared pool."""

    protocol_version = "HTTP/1.1"
    pool: BackendPool
    metrics: LoadBalancerMetrics
    observer: ProxyObserver
    control_plane: ControlPlaneService
    upstream_transport: UpstreamTransport
    response_relay: ResponseRelay
    max_retries = 1
    max_request_body_bytes = 1_048_576

    def do_GET(self) -> None:
        """Forward one GET request or return a controlled gateway error."""

        if self._content_length("GET", allow_body=False) is None:
            return
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

        body = self._read_request_body("POST")
        if body is None:
            return

        backend_action = self._parse_backend_action()
        if backend_action is not None:
            name, action = backend_action
            self._apply_backend_action(name, action)
            return

        if self._is_internal_path():
            self._send_body(405, b"Internal endpoint is read-only\n")
            return

        self._proxy_request("POST", body)

    def do_DELETE(self) -> None:
        """Forward one bounded DELETE request body."""

        self._proxy_body_request("DELETE")

    def _proxy_body_request(self, method: str) -> None:
        """Read and proxy a bounded request unless its path is internal."""

        body = self._read_request_body(method)
        if body is None:
            return
        if self._is_internal_path():
            self._send_body(405, b"Internal endpoint is read-only\n")
            return
        self._proxy_request(method, body)

    def _read_request_body(self, method: str) -> bytes | None:
        """Read a declared body within the configured memory bound."""

        content_length = self._content_length(method, allow_body=True)
        if content_length is None:
            return None

        if content_length > self.max_request_body_bytes:
            self._reject_request(
                method,
                413,
                b"Request body exceeds configured limit\n",
                "request_body_too_large",
            )
            return None

        started_at = perf_counter()
        try:
            body = self.rfile.read(content_length)
        except ConnectionError:
            body = b""
        if len(body) != content_length:
            self._record_client_disconnect(
                method,
                backend=None,
                started_at=started_at,
                request_id=self._request_id(),
            )
            return None
        return body

    def _content_length(self, method: str, *, allow_body: bool) -> int | None:
        """Validate supported HTTP/1.1 request framing and return its length."""

        try:
            return request_content_length(
                self.headers,
                allow_body=allow_body,
            )
        except RequestFramingError as error:
            self._reject_request(
                method,
                error.status,
                error.body,
                error.outcome,
            )
            return None

    def _reject_request(
        self,
        method: str,
        status: int,
        body: bytes,
        outcome: str,
    ) -> None:
        """Reject unsafe request framing and close without reading more bytes."""

        request_id = self._request_id()
        started_at = perf_counter()
        self.close_connection = True
        self._send_body(status, body, request_id=request_id)
        self._record_completion(
            method,
            status,
            None,
            outcome,
            started_at,
            request_id,
        )

    def _is_internal_path(self) -> bool:
        """Return whether the current target belongs to the local control plane."""

        return urlsplit(self.path).path in {ADMIN_BACKENDS_PATH, METRICS_PATH}

    def _proxy_request(self, method: str, body: bytes | None = None) -> None:
        """Select a backend and relay one supported HTTP request."""

        started_at = perf_counter()
        request_id = self._request_id()
        attempted_backends: set[str] = set()
        last_failure: UpstreamFailure | None = None
        failed_backend: Backend | None = None

        for attempt in range(self.max_retries + 1):
            backend = self.pool.acquire(exclude=attempted_backends)
            if backend is None:
                if last_failure is None:
                    self._send_body(
                        503,
                        b"No healthy backends available\n",
                        request_id=request_id,
                    )
                    self._record_completion(
                        method,
                        503,
                        None,
                        "no_healthy_backend",
                        started_at,
                        request_id,
                    )
                else:
                    self._send_body(
                        502,
                        b"Selected backend could not be reached\n",
                        request_id=request_id,
                    )
                    self._record_completion(
                        method,
                        502,
                        failed_backend,
                        last_failure.outcome,
                        started_at,
                        request_id,
                    )
                return

            if last_failure is not None and failed_backend is not None:
                self.observer.record_retry(
                    method,
                    last_failure.outcome,
                    failed_backend,
                )
            attempted_backends.add(backend.name)
            try:
                try:
                    status, delivery_outcome = self._forward(
                        method,
                        backend,
                        body,
                        request_id,
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

                    self._send_body(
                        502,
                        b"Selected backend could not be reached\n",
                        request_id=request_id,
                    )
                    self._record_completion(
                        method,
                        502,
                        backend,
                        failure.outcome,
                        started_at,
                        request_id,
                    )
                    return

                if delivery_outcome == "client_disconnected":
                    self._record_client_disconnect(
                        method,
                        backend=backend,
                        started_at=started_at,
                        request_id=request_id,
                    )
                    return
                if delivery_outcome is not None:
                    self.close_connection = True
                    self._record_completion(
                        method,
                        502,
                        backend,
                        delivery_outcome,
                        started_at,
                        request_id,
                    )
                    return
                outcome = "completed_after_retry" if attempt > 0 else "completed"
                self._record_completion(
                    method,
                    status,
                    backend,
                    outcome,
                    started_at,
                    request_id,
                )
                return
            finally:
                self.pool.release(backend.name)

    def _send_upstream_headers(
        self,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        content_length: int,
        request_id: str,
    ) -> bool:
        """Send filtered response headers with explicit downstream framing."""

        try:
            self.send_response(status, reason)
            for name, value in forwarded_response_headers(headers):
                self.send_header(name, value)
            self.send_header("Content-Length", str(content_length))
            self.send_header("X-Request-Id", request_id)
            self.end_headers()
        except ConnectionError:
            self.close_connection = True
            return False
        return True

    def _write_response_body(self, body: bytes) -> bool:
        """Write response bytes unless the downstream client has disconnected."""

        try:
            self.wfile.write(body)
        except ConnectionError:
            self.close_connection = True
            return False
        return True

    def _record_client_disconnect(
        self,
        method: str,
        *,
        backend: Backend | None,
        started_at: float,
        request_id: str,
    ) -> None:
        """Record an interrupted client connection without raising."""

        self.close_connection = True
        self._record_completion(
            method,
            499,
            backend,
            "client_disconnected",
            started_at,
            request_id,
        )

    def _forward(
        self,
        method: str,
        backend: Backend,
        body: bytes | None,
        request_id: str,
    ) -> tuple[int, str | None]:
        """Send a request upstream and relay its bounded response."""

        request = UpstreamRequest(
            method=method,
            path=self.path,
            body=body,
            headers=tuple(self.headers.items()),
            client_ip=self.client_address[0],
            original_host=self.headers.get("Host"),
            request_id=request_id,
        )
        with self.upstream_transport.send(backend, request) as response:
            result = self.response_relay.relay(response, request_id, self)
        return result.status, result.outcome

    def _send_backend_snapshot(self) -> None:
        """Return the current backend state without changing routing."""

        body = json.dumps(
            [view.as_dict() for view in self.control_plane.list_backends()]
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
            view = self.control_plane.apply_backend_action(name, action)
        except KeyError:
            self._send_body(404, b"Unknown backend\n")
            return

        body = json.dumps(view.as_dict(include_url=False)).encode()
        self._send_body(200, body, content_type="application/json")

    def _send_body(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = "text/plain; charset=utf-8",
        request_id: str | None = None,
    ) -> None:
        """Send a small response with an explicit content type and body length."""

        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if request_id is not None:
                self.send_header("X-Request-Id", request_id)
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            self.close_connection = True

    def _record_completion(
        self,
        method: str,
        status: int,
        backend: Backend | None,
        outcome: str,
        started_at: float,
        request_id: str,
    ) -> None:
        """Record metrics and write one log for a completed proxy request."""

        self.observer.record_completion(
            method=method,
            path=self.path,
            status=status,
            backend=backend,
            outcome=outcome,
            started_at=started_at,
            request_id=request_id,
        )

    def _request_id(self) -> str:
        """Return a safe client correlation ID or generate a new UUID."""

        supplied = self.headers.get("X-Request-Id")
        if supplied is not None and REQUEST_ID_PATTERN.fullmatch(supplied):
            return supplied
        return str(uuid4())

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base handler's duplicate unstructured access log."""


def create_proxy_server(
    address: tuple[str, int],
    pool: BackendPool,
    *,
    upstream_connect_timeout: float = 2.0,
    upstream_response_timeout: float = 2.0,
    max_retries: int = 1,
    max_request_body_bytes: int = 1_048_576,
    max_response_body_bytes: int = 1_048_576,
    metrics: LoadBalancerMetrics | None = None,
    control_plane: ControlPlaneService | None = None,
    observer: ProxyObserver | None = None,
    upstream_transport: UpstreamTransport | None = None,
    response_relay: ResponseRelay | None = None,
) -> ProxyHTTPServer:
    """Create a threaded server whose handlers share one backend pool."""

    proxy_metrics = metrics or LoadBalancerMetrics()
    handler_class = type(
        "ConfiguredProxyRequestHandler",
        (ProxyRequestHandler,),
        {
            "pool": pool,
            "metrics": proxy_metrics,
            "observer": observer or ProxyObserver(proxy_metrics),
            "control_plane": control_plane or ControlPlaneService(pool),
            "upstream_transport": upstream_transport or UpstreamTransport(
                connect_timeout=upstream_connect_timeout,
                response_timeout=upstream_response_timeout,
                connection_factory=HTTPConnection,
            ),
            "response_relay": response_relay
            or ResponseRelay(max_response_body_bytes),
            "max_retries": max_retries,
            "max_request_body_bytes": max_request_body_bytes,
        },
    )
    return ProxyHTTPServer(address, handler_class)
