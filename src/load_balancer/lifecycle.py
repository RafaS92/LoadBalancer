"""Reusable lifecycle management for threaded HTTP services."""

from __future__ import annotations

import signal
from collections.abc import Sequence
from threading import Event, Thread
from typing import Protocol


class ManagedServer(Protocol):
    """Server operations required by the process lifecycle."""

    def serve_forever(self) -> None: ...

    def shutdown(self) -> None: ...

    def server_close(self) -> None: ...


class BackgroundService(Protocol):
    """Start/stop lifecycle shared by health checks and future workers."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


def run_until_shutdown(
    server: ManagedServer,
    *,
    background_services: Sequence[BackgroundService] = (),
    shutdown_event: Event | None = None,
    install_signal_handlers: bool = True,
    thread_name: str = "http-server",
) -> None:
    """Run a server until interrupted, then close all resources in order."""

    requested = shutdown_event or Event()
    previous_handlers: dict[signal.Signals, signal.Handlers] = {}

    def request_shutdown(signum: int, frame: object) -> None:
        del signum, frame
        requested.set()

    if install_signal_handlers:
        for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[shutdown_signal] = signal.signal(
                shutdown_signal,
                request_shutdown,
            )

    server_errors: list[BaseException] = []

    def serve() -> None:
        try:
            server.serve_forever()
        except BaseException as error:
            server_errors.append(error)
        finally:
            requested.set()

    server_thread = Thread(target=serve, name=thread_name)
    started_services: list[BackgroundService] = []
    server_started = False
    try:
        for service in background_services:
            service.start()
            started_services.append(service)
        server_thread.start()
        server_started = True
        requested.wait()
    except KeyboardInterrupt:
        requested.set()
    finally:
        if server_started:
            server.shutdown()
            server_thread.join()
        server.server_close()
        for service in reversed(started_services):
            service.stop()
        for shutdown_signal, previous_handler in previous_handlers.items():
            signal.signal(shutdown_signal, previous_handler)

    if server_errors:
        raise server_errors[0]
