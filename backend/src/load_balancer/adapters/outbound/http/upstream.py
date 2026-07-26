"""Standard-library HTTP transport for selected backend requests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPException, HTTPResponse
from urllib.parse import urlsplit

from load_balancer.domain.models import Backend
from load_balancer.infrastructure.defaults import (
    FORWARDED_HEADERS,
    HOP_BY_HOP_HEADERS,
)
from load_balancer.ports.upstream import UpstreamFailure, UpstreamRequest

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
