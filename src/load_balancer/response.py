"""Bounded backend response delivery independent of request routing."""

from __future__ import annotations

from dataclasses import dataclass
from http.client import HTTPException, HTTPResponse
from typing import Protocol

from load_balancer.upstream import HOP_BY_HOP_HEADERS, UpstreamFailure

RESPONSE_CHUNK_SIZE = 64 * 1024


class DownstreamResponseWriter(Protocol):
    """Operations the response policy needs from an HTTP adapter."""

    def _send_upstream_headers(
        self,
        status: int,
        reason: str,
        headers: list[tuple[str, str]],
        content_length: int,
        request_id: str,
    ) -> bool: ...

    def _write_response_body(self, body: bytes) -> bool: ...


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Result of delivering one upstream response downstream."""

    status: int
    outcome: str | None = None


class ResponseRelay:
    """Enforce response limits while streaming whenever framing permits."""

    def __init__(self, max_body_bytes: int) -> None:
        if max_body_bytes <= 0:
            raise ValueError("maximum response body bytes must be positive")
        self._max_body_bytes = max_body_bytes

    def relay(
        self,
        response: HTTPResponse,
        request_id: str,
        downstream: DownstreamResponseWriter,
    ) -> DeliveryResult:
        """Deliver a bounded response and classify mid-stream failures."""

        status = response.status
        reason = response.reason
        headers = response.getheaders()
        has_no_body = 100 <= status < 200 or status in {204, 304}
        if has_no_body:
            content_length = 0
        elif response.chunked:
            content_length = None
        else:
            content_length = response_content_length(headers)

        if content_length is None:
            response_body = self._read_unframed(response)
            if not downstream._send_upstream_headers(
                status,
                reason,
                headers,
                len(response_body),
                request_id,
            ):
                return DeliveryResult(status, "client_disconnected")
            if not downstream._write_response_body(response_body):
                return DeliveryResult(status, "client_disconnected")
            return DeliveryResult(status)

        if content_length > self._max_body_bytes:
            raise UpstreamFailure("backend_response_too_large")
        if not downstream._send_upstream_headers(
            status,
            reason,
            headers,
            content_length,
            request_id,
        ):
            return DeliveryResult(status, "client_disconnected")

        remaining = content_length
        while remaining:
            try:
                chunk = response.read1(min(RESPONSE_CHUNK_SIZE, remaining))
            except TimeoutError:
                return DeliveryResult(status, "backend_response_timeout")
            except (OSError, HTTPException):
                return DeliveryResult(status, "backend_response_failed")
            if not chunk:
                return DeliveryResult(status, "backend_response_failed")
            if not downstream._write_response_body(chunk):
                return DeliveryResult(status, "client_disconnected")
            remaining -= len(chunk)
        return DeliveryResult(status)

    def _read_unframed(self, response: HTTPResponse) -> bytes:
        """Buffer an unframed response within the configured safety limit."""

        try:
            body = response.read(self._max_body_bytes + 1)
        except TimeoutError as error:
            raise UpstreamFailure("backend_response_timeout") from error
        except (OSError, HTTPException) as error:
            raise UpstreamFailure("backend_response_failed") from error
        if len(body) > self._max_body_bytes:
            raise UpstreamFailure("backend_response_too_large")
        return body


def response_content_length(headers: list[tuple[str, str]]) -> int | None:
    """Return one valid backend Content-Length or reject ambiguous framing."""

    values = [
        value for name, value in headers if name.lower() == "content-length"
    ]
    if not values:
        return None
    if len(values) > 1:
        raise UpstreamFailure("backend_response_failed")
    try:
        content_length = int(values[0])
    except ValueError as error:
        raise UpstreamFailure("backend_response_failed") from error
    if content_length < 0:
        raise UpstreamFailure("backend_response_failed")
    return content_length


def forwarded_response_headers(
    headers: list[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """Filter headers that cannot be forwarded across a proxy boundary."""

    return tuple(
        (name, value)
        for name, value in headers
        if name.lower() not in HOP_BY_HOP_HEADERS
        and name.lower() not in {"content-length", "x-request-id"}
    )
