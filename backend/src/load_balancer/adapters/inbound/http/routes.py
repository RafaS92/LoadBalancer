"""Endpoint matching kept separate from request execution."""

from urllib.parse import unquote, urlsplit

from load_balancer.infrastructure.defaults import (
    ADMIN_BACKENDS_PATH,
    DASHBOARD_PATH,
    METRICS_PATH,
)

INTERNAL_PATHS = frozenset(
    {ADMIN_BACKENDS_PATH, METRICS_PATH, DASHBOARD_PATH}
)


def request_path(target: str) -> str:
    return urlsplit(target).path


def is_internal_path(target: str) -> bool:
    return request_path(target) in INTERNAL_PATHS


def parse_backend_action(target: str) -> tuple[str, str] | None:
    parts = request_path(target).split("/")
    if (
        len(parts) != 5
        or parts[:3] != ["", "admin", "backends"]
        or not parts[3]
        or parts[4] not in {"enable", "disable", "drain"}
    ):
        return None
    return unquote(parts[3]), parts[4]
