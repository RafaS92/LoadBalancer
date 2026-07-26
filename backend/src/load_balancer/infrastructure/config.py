"""Command-line configuration for the load balancer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlsplit

from load_balancer.domain.models import Backend
from load_balancer.infrastructure.defaults import (
    DEFAULT_BACKEND_DEFINITIONS,
    DEFAULT_HEALTH_FAILURE_THRESHOLD,
    DEFAULT_HEALTH_INTERVAL,
    DEFAULT_HEALTH_PATH,
    DEFAULT_HEALTH_SUCCESS_THRESHOLD,
    DEFAULT_HEALTH_TIMEOUT,
    DEFAULT_LISTEN_HOST,
    DEFAULT_LISTEN_PORT,
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    DEFAULT_MAX_RESPONSE_BODY_BYTES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_ROUTING_STRATEGY,
    DEFAULT_UPSTREAM_CONNECT_TIMEOUT,
    DEFAULT_UPSTREAM_RESPONSE_TIMEOUT,
    ROUTING_STRATEGIES,
)
from load_balancer.infrastructure.validation import (
    non_negative_integer_argument,
    port_argument,
    positive_float_argument,
    positive_integer_argument,
)

DEFAULT_BACKENDS = tuple(
    Backend(name, url) for name, url in DEFAULT_BACKEND_DEFINITIONS
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


def health_path_argument(value: str) -> str:
    if not value.startswith("/") or value.startswith("//"):
        raise argparse.ArgumentTypeError("health path must start with one /")
    return value


def parse_settings(arguments: Sequence[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser(description="Run the learning load balancer")
    parser.add_argument("--listen-host", default=DEFAULT_LISTEN_HOST)
    parser.add_argument(
        "--listen-port", type=port_argument, default=DEFAULT_LISTEN_PORT
    )
    parser.add_argument(
        "--strategy",
        choices=ROUTING_STRATEGIES,
        default=DEFAULT_ROUTING_STRATEGY,
    )
    parser.add_argument(
        "--upstream-connect-timeout",
        type=positive_float_argument,
        default=DEFAULT_UPSTREAM_CONNECT_TIMEOUT,
        help="maximum seconds to establish a backend connection",
    )
    parser.add_argument(
        "--upstream-response-timeout",
        type=positive_float_argument,
        default=DEFAULT_UPSTREAM_RESPONSE_TIMEOUT,
        help="maximum seconds to wait on a connected backend",
    )
    parser.add_argument(
        "--max-retries",
        type=non_negative_integer_argument,
        default=DEFAULT_MAX_RETRIES,
        help="additional connection attempts allowed for safe requests",
    )
    parser.add_argument(
        "--max-request-body-bytes",
        type=positive_integer_argument,
        default=DEFAULT_MAX_REQUEST_BODY_BYTES,
        help="maximum accepted request body size in bytes",
    )
    parser.add_argument(
        "--max-response-body-bytes",
        type=positive_integer_argument,
        default=DEFAULT_MAX_RESPONSE_BODY_BYTES,
        help="maximum backend response body size in bytes",
    )
    parser.add_argument(
        "--health-path",
        type=health_path_argument,
        default=DEFAULT_HEALTH_PATH,
    )
    parser.add_argument(
        "--health-interval",
        type=positive_float_argument,
        default=DEFAULT_HEALTH_INTERVAL,
        help="seconds between health-check cycles",
    )
    parser.add_argument(
        "--health-timeout",
        type=positive_float_argument,
        default=DEFAULT_HEALTH_TIMEOUT,
        help="maximum seconds for one health probe",
    )
    parser.add_argument(
        "--health-failure-threshold",
        type=positive_integer_argument,
        default=DEFAULT_HEALTH_FAILURE_THRESHOLD,
        help="consecutive failures required to mark a backend unhealthy",
    )
    parser.add_argument(
        "--health-success-threshold",
        type=positive_integer_argument,
        default=DEFAULT_HEALTH_SUCCESS_THRESHOLD,
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
