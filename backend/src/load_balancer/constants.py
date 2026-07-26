"""Application defaults and protocol policy constants.

Keeping these values in one module makes the load balancer's default behavior
easy to discover without mixing configuration values into runtime logic.
"""

from __future__ import annotations

import re

from load_balancer.routing import Backend

# Load-balancer listener and routing defaults.
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 8080
DEFAULT_ROUTING_STRATEGY = "round-robin"
ROUTING_STRATEGIES = ("round-robin", "least-connections")
DEFAULT_BACKENDS = (
    Backend("backend-a", "http://127.0.0.1:9001"),
    Backend("backend-b", "http://127.0.0.1:9002"),
    Backend("backend-c", "http://127.0.0.1:9003"),
)

# Proxy safety and upstream communication defaults.
DEFAULT_UPSTREAM_CONNECT_TIMEOUT = 2.0
DEFAULT_UPSTREAM_RESPONSE_TIMEOUT = 2.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_MAX_REQUEST_BODY_BYTES = 1_048_576
DEFAULT_MAX_RESPONSE_BODY_BYTES = 1_048_576
RESPONSE_CHUNK_SIZE = 64 * 1024

# Active health-check defaults.
DEFAULT_HEALTH_PATH = "/health"
DEFAULT_HEALTH_INTERVAL = 2.0
DEFAULT_HEALTH_TIMEOUT = 0.5
DEFAULT_HEALTH_FAILURE_THRESHOLD = 2
DEFAULT_HEALTH_SUCCESS_THRESHOLD = 2

# Demo-backend defaults.
DEFAULT_DEMO_BACKEND_NAME = "backend-a"
DEFAULT_DEMO_BACKEND_HOST = "127.0.0.1"
DEFAULT_DEMO_BACKEND_PORT = 9001
DEFAULT_MAX_BODY_BYTES = 1_048_576

# Local operational endpoints.
ADMIN_BACKENDS_PATH = "/admin/backends"
METRICS_PATH = "/metrics"
DASHBOARD_PATH = "/api/v1/dashboard"

# Request retry and identity policy.
RETRYABLE_METHODS = frozenset({"GET"})
RETRYABLE_OUTCOMES = frozenset(
    {"backend_connect_timeout", "backend_connection_failed"}
)
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")

# Headers that must be rebuilt or removed at the proxy boundary.
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
FORWARDED_HEADERS = frozenset(
    {
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
    }
)

# Number of completed requests retained by the in-memory dashboard.
DEFAULT_RECENT_REQUEST_LIMIT = 30
