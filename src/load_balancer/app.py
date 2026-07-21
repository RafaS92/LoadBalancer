"""Application entry point."""

import logging

from load_balancer.config import parse_settings
from load_balancer.health import HealthChecker
from load_balancer.metrics import LoadBalancerMetrics
from load_balancer.proxy import create_proxy_server
from load_balancer.routing import create_pool


def project_status() -> str:
    """Return a message proving that the package can be imported."""
    return "Load balancer project is ready"


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
        metrics=metrics,
    )
    host, port = server.server_address
    print(f"Load balancer listening on http://{host}:{port}")
    health_checker.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        health_checker.stop()
        server.server_close()


if __name__ == "__main__":
    main()
