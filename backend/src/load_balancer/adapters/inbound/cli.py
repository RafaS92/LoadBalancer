"""Command-line inbound adapter for the load-balancer process."""

import logging
from http.server import ThreadingHTTPServer
from threading import Event

from load_balancer.bootstrap import build_application
from load_balancer.infrastructure.config import parse_settings
from load_balancer.infrastructure.lifecycle import (
    BackgroundService,
    run_until_shutdown,
)


def project_status() -> str:
    return "Load balancer project is ready"


def serve_until_shutdown(
    server: ThreadingHTTPServer,
    health_checker: BackgroundService,
    *,
    shutdown_event: Event | None = None,
    install_signal_handlers: bool = True,
) -> None:
    run_until_shutdown(
        server,
        background_services=(health_checker,),
        shutdown_event=shutdown_event,
        install_signal_handlers=install_signal_handlers,
        thread_name="proxy-server",
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = parse_settings()
    application = build_application(settings)
    host, port = application.server.server_address
    print(f"Load balancer listening on http://{host}:{port}")
    serve_until_shutdown(application.server, application.health_checker)
