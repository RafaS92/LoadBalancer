"""Thin downstream HTTP adapter for load-balancer use cases."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler

from prometheus_client import CONTENT_TYPE_LATEST

from load_balancer.adapters.inbound.http.framing import (
    RequestFramingError,
    request_content_length,
)
from load_balancer.adapters.inbound.http.routes import (
    is_internal_path,
    parse_backend_action,
    request_path,
)
from load_balancer.adapters.observability.metrics import LoadBalancerMetrics
from load_balancer.adapters.outbound.http.response import (
    forwarded_response_headers,
)
from load_balancer.application.administration import ControlPlaneService
from load_balancer.application.dashboard import DashboardService
from load_balancer.application.proxying import ProxyService
from load_balancer.infrastructure.defaults import (
    ADMIN_BACKENDS_PATH,
    DASHBOARD_PATH,
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    METRICS_PATH,
    REQUEST_ID_PATTERN_SOURCE,
)
from load_balancer.infrastructure.runtime import (
    SystemClock,
    UUIDRequestIdGenerator,
)
from load_balancer.infrastructure.server import GracefulThreadingHTTPServer
from load_balancer.ports.runtime import Clock, RequestIdGenerator
from load_balancer.ports.upstream import UpstreamRequest

REQUEST_ID_PATTERN = re.compile(REQUEST_ID_PATTERN_SOURCE)


class ProxyHTTPServer(GracefulThreadingHTTPServer):
    """Threaded server that waits for active requests during close."""


class ProxyRequestHandler(BaseHTTPRequestHandler):
    """Translate HTTP requests and responses at the application boundary."""

    protocol_version = "HTTP/1.1"
    proxy_service: ProxyService
    metrics: LoadBalancerMetrics
    control_plane: ControlPlaneService
    dashboard: DashboardService
    request_ids: RequestIdGenerator = UUIDRequestIdGenerator()
    clock: Clock = SystemClock()
    max_request_body_bytes = DEFAULT_MAX_REQUEST_BODY_BYTES

    def do_GET(self) -> None:
        if self._content_length("GET", allow_body=False) is None:
            return
        path = request_path(self.path)
        if path == ADMIN_BACKENDS_PATH:
            self._send_backend_snapshot()
        elif path == METRICS_PATH:
            self.send_body(
                200,
                self.metrics.render(),
                content_type=CONTENT_TYPE_LATEST,
            )
        elif path == DASHBOARD_PATH:
            self._send_dashboard_snapshot()
        else:
            self._proxy_request("GET")

    def do_POST(self) -> None:
        body = self._read_request_body("POST")
        if body is None:
            return
        action = parse_backend_action(self.path)
        if action is not None:
            self._apply_backend_action(*action)
            return
        if is_internal_path(self.path):
            self.send_body(405, b"Internal endpoint is read-only\n")
            return
        self._proxy_request("POST", body)

    def do_DELETE(self) -> None:
        body = self._read_request_body("DELETE")
        if body is None:
            return
        if is_internal_path(self.path):
            self.send_body(405, b"Internal endpoint is read-only\n")
            return
        self._proxy_request("DELETE", body)

    def _read_request_body(self, method: str) -> bytes | None:
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

        started_at = self.clock.now()
        try:
            body = self.rfile.read(content_length)
        except ConnectionError:
            body = b""
        if len(body) != content_length:
            self.close()
            request = self._request(method)
            self.proxy_service.record_client_disconnect(
                request,
                started_at=started_at,
            )
            return None
        return body

    def _content_length(self, method: str, *, allow_body: bool) -> int | None:
        try:
            return request_content_length(self.headers, allow_body=allow_body)
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
        started_at = self.clock.now()
        request = self._request(method)
        self.close()
        self.send_body(status, body, request_id=request.request_id)
        self.proxy_service.record_rejection(
            request,
            status=status,
            outcome=outcome,
            started_at=started_at,
        )

    def _proxy_request(self, method: str, body: bytes | None = None) -> None:
        self.proxy_service.execute(self._request(method, body), self)

    def _request(
        self,
        method: str,
        body: bytes | None = None,
    ) -> UpstreamRequest:
        return UpstreamRequest(
            method=method,
            path=self.path,
            body=body,
            headers=tuple(self.headers.items()),
            client_ip=self.client_address[0],
            original_host=self.headers.get("Host"),
            request_id=self._request_id(),
        )

    def _send_backend_snapshot(self) -> None:
        body = json.dumps(
            [view.as_dict() for view in self.control_plane.list_backends()]
        ).encode()
        self.send_body(200, body, content_type="application/json")

    def _send_dashboard_snapshot(self) -> None:
        body = json.dumps(
            self.dashboard.snapshot(),
            separators=(",", ":"),
        ).encode()
        self.send_body(
            200,
            body,
            content_type="application/json",
            cache_control="no-store",
        )

    def _apply_backend_action(self, name: str, action: str) -> None:
        try:
            view = self.control_plane.apply_backend_action(name, action)
        except KeyError:
            self.send_body(404, b"Unknown backend\n")
            return
        body = json.dumps(view.as_dict(include_url=False)).encode()
        self.send_body(200, body, content_type="application/json")

    def send_body(
        self,
        status: int,
        body: bytes,
        *,
        request_id: str | None = None,
        content_type: str = "text/plain; charset=utf-8",
        cache_control: str | None = None,
    ) -> bool:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if request_id is not None:
                self.send_header("X-Request-Id", request_id)
            if cache_control is not None:
                self.send_header("Cache-Control", cache_control)
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            self.close()
            return False
        return True

    def send_upstream_headers(
        self,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        content_length: int,
        request_id: str,
    ) -> bool:
        return self._send_upstream_headers(
            status, reason, headers, content_length, request_id
        )

    def _send_upstream_headers(
        self,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        content_length: int,
        request_id: str,
    ) -> bool:
        try:
            self.send_response(status, reason)
            for name, value in forwarded_response_headers(headers):
                self.send_header(name, value)
            self.send_header("Content-Length", str(content_length))
            self.send_header("X-Request-Id", request_id)
            self.end_headers()
        except ConnectionError:
            self.close()
            return False
        return True

    def write_body(self, body: bytes) -> bool:
        return self._write_response_body(body)

    def _write_response_body(self, body: bytes) -> bool:
        try:
            self.wfile.write(body)
        except ConnectionError:
            self.close_connection = True
            return False
        return True

    def close(self) -> None:
        self.close_connection = True

    def _request_id(self) -> str:
        supplied = self.headers.get("X-Request-Id")
        if supplied is not None and REQUEST_ID_PATTERN.fullmatch(supplied):
            return supplied
        return self.request_ids.new()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base handler's duplicate access log."""


def create_http_server(
    address: tuple[str, int],
    *,
    proxy_service: ProxyService,
    metrics: LoadBalancerMetrics,
    control_plane: ControlPlaneService,
    dashboard: DashboardService,
    max_request_body_bytes: int,
    request_ids: RequestIdGenerator | None = None,
    clock: Clock | None = None,
) -> ProxyHTTPServer:
    """Create the HTTP adapter with explicitly composed dependencies."""

    handler_class = type(
        "ConfiguredProxyRequestHandler",
        (ProxyRequestHandler,),
        {
            "proxy_service": proxy_service,
            "metrics": metrics,
            "control_plane": control_plane,
            "dashboard": dashboard,
            "max_request_body_bytes": max_request_body_bytes,
            "request_ids": request_ids or UUIDRequestIdGenerator(),
            "clock": clock or SystemClock(),
        },
    )
    return ProxyHTTPServer(address, handler_class)
