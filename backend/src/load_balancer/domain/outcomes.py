"""Typed operational outcomes produced by application services."""

from enum import StrEnum


class ProxyOutcome(StrEnum):
    """Stable outcome labels shared by logs, metrics, and the dashboard."""

    COMPLETED = "completed"
    COMPLETED_AFTER_RETRY = "completed_after_retry"
    NO_HEALTHY_BACKEND = "no_healthy_backend"
    CLIENT_DISCONNECTED = "client_disconnected"
    BACKEND_CONNECT_TIMEOUT = "backend_connect_timeout"
    BACKEND_CONNECTION_FAILED = "backend_connection_failed"
    BACKEND_RESPONSE_TIMEOUT = "backend_response_timeout"
    BACKEND_RESPONSE_FAILED = "backend_response_failed"
    BACKEND_RESPONSE_TOO_LARGE = "backend_response_too_large"


RETRYABLE_OUTCOMES = frozenset(
    {
        ProxyOutcome.BACKEND_CONNECT_TIMEOUT,
        ProxyOutcome.BACKEND_CONNECTION_FAILED,
    }
)
