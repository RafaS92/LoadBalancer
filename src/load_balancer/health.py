"""Active backend health checking."""

from __future__ import annotations

from threading import Event, Thread

import httpx

from load_balancer.routing import Backend, RoundRobinPool


class HealthChecker:
    """Periodically update a pool by probing every configured backend."""

    def __init__(
        self,
        pool: RoundRobinPool,
        *,
        path: str = "/health",
        interval: float = 2.0,
        timeout: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        if not path.startswith("/"):
            raise ValueError("health path must start with /")
        if interval <= 0 or timeout <= 0:
            raise ValueError("health interval and timeout must be positive")

        self._pool = pool
        self._path = path
        self._interval = interval
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._stop_event = Event()
        self._thread: Thread | None = None

    def check_once(self) -> None:
        """Run one complete health-check cycle."""

        for status in self._pool.snapshot():
            healthy = self._probe(status.backend)
            self._pool.set_health(status.backend.name, healthy=healthy)

    def start(self) -> None:
        """Start checking in a background thread."""

        if self._thread is not None:
            raise RuntimeError("health checker is already running")
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            name="backend-health-checker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background thread and wait for it to finish."""

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        if self._owns_client:
            self._client.close()

    def _run(self) -> None:
        """Check immediately, then wait between later cycles."""

        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self._interval)

    def _probe(self, backend: Backend) -> bool:
        """Return whether one backend responds successfully to the health path."""

        try:
            response = self._client.get(f"{backend.url.rstrip('/')}{self._path}")
            return response.is_success
        except httpx.HTTPError:
            return False
