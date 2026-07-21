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
    upstream_connect_timeout: float
    upstream_response_timeout: float
    max_retries: int
    max_request_body_bytes: int
    max_response_body_bytes: int
    backends: tuple[Backend, ...]
    health_path: str
    health_interval: float
    health_timeout: float
    health_failure_threshold: int
    health_success_threshold: int
    strategy: str


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


def positive_float_argument(value: str) -> float:
    """Parse a positive number of seconds."""

    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a number") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def positive_integer_argument(value: str) -> int:
    """Parse a positive whole number."""

    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def non_negative_integer_argument(value: str) -> int:
    """Parse a whole number that may be zero."""

    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be an integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return number


def health_path_argument(value: str) -> str:
    """Parse an absolute HTTP path used for backend probes."""

    if not value.startswith("/") or value.startswith("//"):
        raise argparse.ArgumentTypeError("health path must start with one /")
    return value


def parse_settings(arguments: Sequence[str] | None = None) -> Settings:
    """Parse command-line arguments into validated settings."""

    parser = argparse.ArgumentParser(description="Run the learning load balancer")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=port_argument, default=8080)
    parser.add_argument(
        "--strategy",
        choices=("round-robin", "least-connections"),
        default="round-robin",
    )
    parser.add_argument(
        "--upstream-connect-timeout",
        type=positive_float_argument,
        default=2.0,
        help="maximum seconds to establish a backend connection",
    )
    parser.add_argument(
        "--upstream-response-timeout",
        type=positive_float_argument,
        default=2.0,
        help="maximum seconds to wait on a connected backend",
    )
    parser.add_argument(
        "--max-retries",
        type=non_negative_integer_argument,
        default=1,
        help="additional connection attempts allowed for safe requests",
    )
    parser.add_argument(
        "--max-request-body-bytes",
        type=positive_integer_argument,
        default=1_048_576,
        help="maximum accepted request body size in bytes",
    )
    parser.add_argument(
        "--max-response-body-bytes",
        type=positive_integer_argument,
        default=1_048_576,
        help="maximum buffered backend response body size in bytes",
    )
    parser.add_argument("--health-path", type=health_path_argument, default="/health")
    parser.add_argument(
        "--health-interval",
        type=positive_float_argument,
        default=2.0,
        help="seconds between health-check cycles",
    )
    parser.add_argument(
        "--health-timeout",
        type=positive_float_argument,
        default=0.5,
        help="maximum seconds for one health probe",
    )
    parser.add_argument(
        "--health-failure-threshold",
        type=positive_integer_argument,
        default=2,
        help="consecutive failures required to mark a backend unhealthy",
    )
    parser.add_argument(
        "--health-success-threshold",
        type=positive_integer_argument,
        default=2,
        help="consecutive successes required to restore a backend",
    )
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

    return Settings(
        listen_host=parsed.listen_host,
        listen_port=parsed.listen_port,
        upstream_connect_timeout=parsed.upstream_connect_timeout,
        upstream_response_timeout=parsed.upstream_response_timeout,
        max_retries=parsed.max_retries,
        max_request_body_bytes=parsed.max_request_body_bytes,
        max_response_body_bytes=parsed.max_response_body_bytes,
        backends=backends,
        health_path=parsed.health_path,
        health_interval=parsed.health_interval,
        health_timeout=parsed.health_timeout,
        health_failure_threshold=parsed.health_failure_threshold,
        health_success_threshold=parsed.health_success_threshold,
        strategy=parsed.strategy,
    )
