"""Small runtime ports for deterministic application behavior."""

from typing import Protocol


class Clock(Protocol):
    """Return a monotonic timestamp in seconds."""

    def now(self) -> float: ...


class RequestIdGenerator(Protocol):
    """Create a new request correlation identifier."""

    def new(self) -> str: ...
