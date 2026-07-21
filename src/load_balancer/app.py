"""Application entry point."""

import logging
import signal
from http.server import ThreadingHTTPServer
from threading import Event, Thread

from load_balancer.config import parse_settings
from load_balancer.health import HealthChecker
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.proxy import create_proxy_server
from load_balancer.routing import create_pool


def project_status() -> str:
    """Return a message proving that the package can be imported."""
    return "Load balancer project is ready"


def serve_until_shutdown(
    server: ThreadingHTTPServer,
    health_checker: HealthChecker,
    *,
    shutdown_event: Event | None = None,
    install_signal_handlers: bool = True,
) -> None:
    """Serve until interrupted, then stop accepting and finish active work."""

    requested = shutdown_event or Event()
    previous_handlers: dict[signal.Signals, signal.Handlers] = {}

    def request_shutdown(
        signum: int,
        frame: object,
    ) -> None:
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

    server_thread = Thread(
        target=serve,
        name="proxy-server",
    )
    health_started = False
    server_started = False
    try:
        health_checker.start()
        health_started = True
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
        if health_started:
            health_checker.stop()
        for shutdown_signal, previous_handler in previous_handlers.items():
            signal.signal(shutdown_signal, previous_handler)

    if server_errors:
        raise server_errors[0]


def main() -> None:
    """Run the proxy using validated command-line settings."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = parse_settings()
    pool = create_pool(list(settings.backends), settings.strategy)
    metrics = LoadBalancerMetrics()
    health_checker = HealthChecker(
        pool,
        path=settings.health_path,
        interval=settings.health_interval,
        timeout=settings.health_timeout,
        failure_threshold=settings.health_failure_threshold,
        success_threshold=settings.health_success_threshold,
        metrics=metrics,
    )
    server = create_proxy_server(
        (settings.listen_host, settings.listen_port),
        pool,
        upstream_connect_timeout=settings.upstream_connect_timeout,
        upstream_response_timeout=settings.upstream_response_timeout,
        max_retries=settings.max_retries,
        max_request_body_bytes=settings.max_request_body_bytes,
        max_response_body_bytes=settings.max_response_body_bytes,
        metrics=metrics,
    )
    host, port = server.server_address
    print(f"Load balancer listening on http://{host}:{port}")
    serve_until_shutdown(server, health_checker)


if __name__ == "__main__":
    main()
