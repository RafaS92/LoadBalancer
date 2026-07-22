"""Thread-safe read models for the operations dashboard."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from threading import Lock

from load_balancer.control_plane import ControlPlaneService
from load_balancer.routing import Backend


def utc_timestamp() -> str:
    """Return an ISO-8601 timestamp suitable for JSON responses."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class DashboardReadModel:
    """Maintain bounded operational aggregates for browser consumption."""

    def __init__(self, *, recent_request_limit: int = 30) -> None:
        if recent_request_limit <= 0:
            raise ValueError("recent request limit must be positive")
        self._lock = Lock()
        self._requests_total = 0
        self._failures_total = 0
        self._retries_total = 0
        self._duration_total_ms = 0.0
        self._backend_stats: dict[str, dict[str, float | int]] = {}
        self._recent_requests: deque[dict[str, object]] = deque(
            maxlen=recent_request_limit
        )

    def record_completion(
        self,
        *,
        method: str,
        path: str,
        status: int,
        backend: Backend | None,
        outcome: str,
        duration_seconds: float,
        request_id: str,
    ) -> None:
        """Add one completed request to dashboard aggregates."""

        duration_ms = duration_seconds * 1000
        failed = status >= 400
        backend_name = backend.name if backend is not None else None
        with self._lock:
            self._requests_total += 1
            self._duration_total_ms += duration_ms
            if failed:
                self._failures_total += 1
            if backend_name is not None:
                stats = self._stats_for(backend_name)
                stats["requests_total"] += 1
                stats["duration_total_ms"] += duration_ms
                if failed:
                    stats["failures_total"] += 1
            self._recent_requests.appendleft(
                {
                    "occurred_at": utc_timestamp(),
                    "method": method,
                    "path": path,
                    "status": status,
                    "backend": backend_name,
                    "outcome": outcome,
                    "duration_ms": round(duration_ms, 3),
                    "request_id": request_id,
                }
            )

    def record_retry(self, backend: Backend) -> None:
        """Add one retry to process and backend aggregates."""

        with self._lock:
            self._retries_total += 1
            self._stats_for(backend.name)["retries_total"] += 1

    def snapshot(self) -> dict[str, object]:
        """Return a detached, JSON-ready view of current traffic data."""

        with self._lock:
            average_latency_ms = (
                self._duration_total_ms / self._requests_total
                if self._requests_total
                else 0.0
            )
            backend_stats = {
                name: self._public_backend_stats(stats)
                for name, stats in self._backend_stats.items()
            }
            return {
                "requests_total": self._requests_total,
                "failures_total": self._failures_total,
                "retries_total": self._retries_total,
                "average_latency_ms": round(average_latency_ms, 3),
                "backend_stats": backend_stats,
                "recent_requests": [
                    dict(request) for request in self._recent_requests
                ],
            }

    def _stats_for(self, backend_name: str) -> dict[str, float | int]:
        return self._backend_stats.setdefault(
            backend_name,
            {
                "requests_total": 0,
                "failures_total": 0,
                "retries_total": 0,
                "duration_total_ms": 0.0,
            },
        )

    @staticmethod
    def _public_backend_stats(
        stats: dict[str, float | int],
    ) -> dict[str, float | int]:
        requests_total = int(stats["requests_total"])
        duration_total_ms = float(stats["duration_total_ms"])
        average_latency_ms = (
            duration_total_ms / requests_total if requests_total else 0.0
        )
        return {
            "requests_total": requests_total,
            "failures_total": int(stats["failures_total"]),
            "retries_total": int(stats["retries_total"]),
            "average_latency_ms": round(average_latency_ms, 3),
        }


class DashboardService:
    """Combine live backend state with bounded traffic observations."""

    def __init__(
        self,
        control_plane: ControlPlaneService,
        traffic: DashboardReadModel,
    ) -> None:
        self._control_plane = control_plane
        self._traffic = traffic

    def snapshot(self) -> dict[str, object]:
        """Return the complete frontend-facing dashboard document."""

        backends = self._control_plane.list_backends()
        traffic = self._traffic.snapshot()
        backend_stats = traffic["backend_stats"]
        assert isinstance(backend_stats, dict)

        backend_documents = []
        for backend in backends:
            stats = backend_stats.get(backend.name, {})
            backend_documents.append(
                {
                    **backend.as_dict(),
                    "requests_total": stats.get("requests_total", 0),
                    "failures_total": stats.get("failures_total", 0),
                    "retries_total": stats.get("retries_total", 0),
                    "average_latency_ms": stats.get(
                        "average_latency_ms", 0.0
                    ),
                }
            )

        return {
            "generated_at": utc_timestamp(),
            "summary": {
                "backends_total": len(backends),
                "healthy_backends": sum(
                    backend.healthy for backend in backends
                ),
                "available_backends": sum(
                    backend.healthy
                    and backend.enabled
                    and not backend.draining
                    for backend in backends
                ),
                "active_requests": sum(
                    backend.active_requests for backend in backends
                ),
                "requests_total": traffic["requests_total"],
                "failures_total": traffic["failures_total"],
                "retries_total": traffic["retries_total"],
                "average_latency_ms": traffic["average_latency_ms"],
            },
            "backends": backend_documents,
            "recent_requests": traffic["recent_requests"],
        }
