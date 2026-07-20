"""Application entry point."""

from load_balancer.proxy import create_proxy_server
from load_balancer.routing import Backend, RoundRobinPool


def project_status() -> str:
    """Return a message proving that the package can be imported."""
    return "Load balancer project is ready"


def main() -> None:
    """Run a local proxy using the demonstration backend addresses."""

    pool = RoundRobinPool(
        [
            Backend("backend-a", "http://127.0.0.1:9001"),
            Backend("backend-b", "http://127.0.0.1:9002"),
            Backend("backend-c", "http://127.0.0.1:9003"),
        ]
    )
    server = create_proxy_server(("127.0.0.1", 8080), pool)
    print("Load balancer listening on http://127.0.0.1:8080")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
