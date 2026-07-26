"""Threaded scheduling and concurrent execution for backend health checks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread

from load_balancer.application.health import HealthEvaluationService
from load_balancer.domain.routing import BackendPool
from load_balancer.ports.health import HealthProbe


class ThreadedHealthWorker:
    """Probe every backend immediately and then at a fixed interval."""

    def __init__(
        self,
        pool: BackendPool,
        probe: HealthProbe,
        evaluator: HealthEvaluationService,
        *,
        path: str,
        interval: float,
    ) -> None:
        if not path.startswith("/"):
            raise ValueError("health path must start with /")
        if interval <= 0:
            raise ValueError("health interval must be positive")
        self._pool = pool
        self._probe = probe
        self._evaluator = evaluator
        self._path = path
        self._interval = interval
        self._stop_event = Event()
        self._thread: Thread | None = None

    def check_once(self) -> None:
        statuses = self._pool.snapshot()
        with ThreadPoolExecutor(
            max_workers=len(statuses),
            thread_name_prefix="backend-health-probe",
        ) as executor:
            results = executor.map(
                lambda status: self._probe.probe(status.backend, self._path),
                statuses,
            )
            probe_results = tuple(results)
        for status, succeeded in zip(statuses, probe_results, strict=True):
            self._evaluator.apply(
                status.backend.name,
                currently_healthy=status.healthy,
                succeeded=succeeded,
            )

    def start(self) -> None:
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
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self._probe.close()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self._interval)
