"""Bounded backend response delivery."""

from __future__ import annotations

from http.client import HTTPException

from load_balancer.infrastructure.defaults import (
    HOP_BY_HOP_HEADERS,
    RESPONSE_CHUNK_SIZE,
)
from load_balancer.ports.downstream import DeliveryResult, DownstreamWriter
from load_balancer.ports.upstream import UpstreamFailure, UpstreamResponse


class ResponseRelay:
    """Enforce response limits while streaming whenever framing permits."""

    def __init__(self, max_body_bytes: int) -> None:
        if max_body_bytes <= 0:
            raise ValueError("maximum response body bytes must be positive")
        self._max_body_bytes = max_body_bytes

    def relay(
        self,
        response: UpstreamResponse,
        request_id: str,
        downstream: DownstreamWriter,
    ) -> DeliveryResult:
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
            if not downstream.send_upstream_headers(
                status,
                reason,
                headers,
                len(response_body),
                request_id,
            ):
                return DeliveryResult(status, "client_disconnected")
            if not downstream.write_body(response_body):
                return DeliveryResult(status, "client_disconnected")
            return DeliveryResult(status)

        if content_length > self._max_body_bytes:
            raise UpstreamFailure("backend_response_too_large")
        if not downstream.send_upstream_headers(
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
            if not downstream.write_body(chunk):
                return DeliveryResult(status, "client_disconnected")
            remaining -= len(chunk)
        return DeliveryResult(status)

    def _read_unframed(self, response: UpstreamResponse) -> bytes:
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
    return tuple(
        (name, value)
        for name, value in headers
        if name.lower() not in HOP_BY_HOP_HEADERS
        and name.lower() not in {"content-length", "x-request-id"}
    )
