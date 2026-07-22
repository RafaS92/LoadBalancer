"""Backward-compatible imports for the renamed CLI module."""

from load_balancer.cli import main, project_status, serve_until_shutdown

__all__ = ["main", "project_status", "serve_until_shutdown"]


if __name__ == "__main__":
    main()
