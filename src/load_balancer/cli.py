"""Command-line entry point for the load-balancer process."""

import logging
from http.server import ThreadingHTTPServer
from threading import Event

from load_balancer.bootstrap import build_application
from load_balancer.config import parse_settings
from load_balancer.health import HealthChecker
from load_balancer.lifecycle import run_until_shutdown


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

    run_until_shutdown(
        server,
        background_services=(health_checker,),
        shutdown_event=shutdown_event,
        install_signal_handlers=install_signal_handlers,
        thread_name="proxy-server",
    )


def main() -> None:
    """Run the proxy using validated command-line settings."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = parse_settings()
    application = build_application(settings)
    host, port = application.server.server_address
    print(f"Load balancer listening on http://{host}:{port}")
    serve_until_shutdown(application.server, application.health_checker)


if __name__ == "__main__":
    main()
