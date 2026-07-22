"""Pure validation for supported downstream HTTP request framing."""

from __future__ import annotations

from typing import Protocol


class HeaderCollection(Protocol):
    """Header operations needed by request-framing validation."""

    def get(self, name: str, default: str | None = None) -> str | None: ...

    def get_all(self, name: str, failobj: list[str]) -> list[str]: ...


class RequestFramingError(Exception):
    """Describe a safe downstream rejection without coupling to a handler."""

    def __init__(
        self,
        status: int,
        body: bytes,
        outcome: str,
    ) -> None:
        super().__init__(outcome)
        self.status = status
        self.body = body
        self.outcome = outcome


def request_content_length(
    headers: HeaderCollection,
    *,
    allow_body: bool,
) -> int:
    """Return one unambiguous request length or raise a safe rejection."""

    if headers.get("Transfer-Encoding") is not None:
        raise RequestFramingError(
            501,
            b"Transfer-Encoding is not supported\n",
            "unsupported_transfer_encoding",
        )

    raw_lengths = headers.get_all("Content-Length", [])
    if len(raw_lengths) > 1:
        raise RequestFramingError(
            400,
            b"Multiple Content-Length headers are not supported\n",
            "ambiguous_content_length",
        )

    raw_length = raw_lengths[0] if raw_lengths else "0"
    try:
        content_length = int(raw_length)
    except ValueError as error:
        raise RequestFramingError(
            400,
            b"Invalid Content-Length header\n",
            "invalid_content_length",
        ) from error

    if content_length < 0:
        raise RequestFramingError(
            400,
            b"Invalid Content-Length header\n",
            "invalid_content_length",
        )

    if not allow_body and content_length > 0:
        raise RequestFramingError(
            400,
            b"Request body is not supported for this method\n",
            "unsupported_request_body",
        )
    return content_length
