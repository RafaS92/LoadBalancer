"""Application entry point."""

from load_balancer.config import parse_settings
from load_balancer.proxy import create_proxy_server
from load_balancer.routing import RoundRobinPool


def project_status() -> str:
    """Return a message proving that the package can be imported."""
    return "Load balancer project is ready"


def main() -> None:
    """Run the proxy using validated command-line settings."""

    settings = parse_settings()
    pool = RoundRobinPool(list(settings.backends))
    server = create_proxy_server(
        (settings.listen_host, settings.listen_port),
        pool,
    )
    host, port = server.server_address
    print(f"Load balancer listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
