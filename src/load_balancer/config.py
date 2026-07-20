"""Command-line configuration for the load balancer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlsplit

from load_balancer.routing import Backend

DEFAULT_BACKENDS = (
    Backend("backend-a", "http://127.0.0.1:9001"),
    Backend("backend-b", "http://127.0.0.1:9002"),
    Backend("backend-c", "http://127.0.0.1:9003"),
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime settings."""

    listen_host: str
    listen_port: int
    backends: tuple[Backend, ...]


def backend_argument(value: str) -> Backend:
    """Parse one backend written as NAME=http://HOST:PORT."""

    name, separator, url = value.partition("=")
    target = urlsplit(url)
    if (
        not separator
        or not name.strip()
        or target.scheme != "http"
        or target.hostname is None
        or target.path not in {"", "/"}
        or target.query
        or target.fragment
    ):
        raise argparse.ArgumentTypeError(
            "backend must use NAME=http://HOST:PORT format"
        )
    return Backend(name.strip(), url.rstrip("/"))


def port_argument(value: str) -> int:
    """Parse a valid TCP port number."""

    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def parse_settings(arguments: Sequence[str] | None = None) -> Settings:
    """Parse command-line arguments into validated settings."""

    parser = argparse.ArgumentParser(description="Run the learning load balancer")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=port_argument, default=8080)
    parser.add_argument(
        "--backend",
        action="append",
        type=backend_argument,
        help="backend in NAME=http://HOST:PORT format; repeat for each backend",
    )
    parsed = parser.parse_args(arguments)
    backends = tuple(parsed.backend or DEFAULT_BACKENDS)
    names = [backend.name for backend in backends]
    if len(names) != len(set(names)):
        parser.error("backend names must be unique")

    return Settings(parsed.listen_host, parsed.listen_port, backends)
