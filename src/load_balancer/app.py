"""Minimal application entry point."""


def project_status() -> str:
    """Return a message proving that the package can be imported."""
    return "Load balancer project is ready"


def main() -> None:
    """Run the application."""
    print(project_status())


if __name__ == "__main__":
    main()
