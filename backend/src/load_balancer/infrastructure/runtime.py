"""Default implementations of clock and request-ID ports."""

from time import perf_counter
from uuid import uuid4


class SystemClock:
    """Read the process monotonic clock."""

    def now(self) -> float:
        return perf_counter()


class UUIDRequestIdGenerator:
    """Generate UUID4 request correlation identifiers."""

    def new(self) -> str:
        return str(uuid4())
