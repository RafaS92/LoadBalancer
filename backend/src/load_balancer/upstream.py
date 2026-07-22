"""HTTP transport for requests sent from the proxy to one backend."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException, HTTPResponse
from urllib.parse import urlsplit

from load_balancer.routing import Backend

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
FORWARDED_HEADERS = {
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
}


class UpstreamFailure(Exception):
    """Carry a safe operational outcome from upstream communication."""

    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = outcome


@dataclass(frozen=True, slots=True)
class UpstreamRequest:
    """Transport-neutral request data required by the upstream adapter."""

    method: str
    path: str
    body: bytes | None
    headers: tuple[tuple[str, str], ...]
    client_ip: str
    original_host: str | None
    request_id: str


ConnectionFactory = Callable[..., HTTPConnection]


class UpstreamTransport:
    """Open classified HTTP exchanges against configured backends."""

    def __init__(
        self,
        *,
        connect_timeout: float,
        response_timeout: float,
        connection_factory: ConnectionFactory = HTTPConnection,
    ) -> None:
        self._connect_timeout = connect_timeout
        self._response_timeout = response_timeout
        self._connection_factory = connection_factory

    @contextmanager
    def send(
        self,
        backend: Backend,
        request: UpstreamRequest,
    ) -> Iterator[HTTPResponse]:
        """Yield one upstream response and always close its connection."""

        target = urlsplit(backend.url)
        if target.scheme != "http" or target.hostname is None:
            raise ValueError(f"unsupported backend URL: {backend.url}")

        connection = self._connection_factory(
            target.hostname,
            target.port or 80,
            timeout=self._connect_timeout,
        )
        try:
            try:
                connection.connect()
            except TimeoutError as error:
                raise UpstreamFailure("backend_connect_timeout") from error
            except (OSError, HTTPException) as error:
                raise UpstreamFailure("backend_connection_failed") from error

            if connection.sock is None:
                raise UpstreamFailure("backend_connection_failed")
            connection.sock.settimeout(self._response_timeout)
            headers = self._headers_for(target.netloc, request)
            try:
                connection.request(
                    request.method,
                    request.path,
                    body=request.body,
                    headers=headers,
                )
                response = connection.getresponse()
            except TimeoutError as error:
                raise UpstreamFailure("backend_response_timeout") from error
            except (OSError, HTTPException) as error:
                raise UpstreamFailure("backend_response_failed") from error
            yield response
        finally:
            connection.close()

    @staticmethod
    def _headers_for(
        target_host: str,
        request: UpstreamRequest,
    ) -> dict[str, str]:
        """Create trusted upstream headers without forwarding spoofable values."""

        headers = {
            name: value
            for name, value in request.headers
            if name.lower() not in HOP_BY_HOP_HEADERS
            and name.lower() not in {"host", "content-length"}
            and name.lower() not in FORWARDED_HEADERS
            and name.lower() != "x-request-id"
        }
        headers["Host"] = target_host
        headers["X-Forwarded-For"] = request.client_ip
        if request.original_host is not None:
            headers["X-Forwarded-Host"] = request.original_host
        headers["X-Forwarded-Proto"] = "http"
        headers["X-Request-Id"] = request.request_id
        return headers
