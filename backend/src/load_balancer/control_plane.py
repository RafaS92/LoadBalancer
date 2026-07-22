"""Backend administration use cases shared by HTTP and future UI adapters."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from load_balancer.routing import BackendPool, BackendStatus

ADMIN_LOGGER = logging.getLogger("load_balancer.admin")


@dataclass(frozen=True, slots=True)
class BackendView:
    """Stable control-plane representation of one backend."""

    name: str
    url: str
    healthy: bool
    enabled: bool
    draining: bool
    drained: bool
    active_requests: int

    @classmethod
    def from_status(cls, status: BackendStatus) -> BackendView:
        """Create a frontend-ready view from an immutable pool snapshot."""

        return cls(
            name=status.backend.name,
            url=status.backend.url,
            healthy=status.healthy,
            enabled=status.enabled,
            draining=status.draining,
            drained=status.draining and status.active_requests == 0,
            active_requests=status.active_requests,
        )

    def as_dict(self, *, include_url: bool = True) -> dict[str, object]:
        """Serialize the view without exposing domain objects."""

        state: dict[str, object] = {
            "healthy": self.healthy,
            "enabled": self.enabled,
            "draining": self.draining,
            "drained": self.drained,
            "active_requests": self.active_requests,
        }
        if include_url:
            return {
                "name": self.name,
                "url": self.url,
                **state,
            }
        return {"name": self.name, **state}


class ControlPlaneService:
    """Expose backend state and operator actions independently of HTTP."""

    def __init__(self, pool: BackendPool) -> None:
        self._pool = pool

    def list_backends(self) -> tuple[BackendView, ...]:
        """Return one consistent view of all configured backends."""

        return tuple(
            BackendView.from_status(status) for status in self._pool.snapshot()
        )

    def apply_backend_action(self, name: str, action: str) -> BackendView:
        """Apply an enable, disable, or drain action and return its new state."""

        if action == "drain":
            self._pool.begin_drain(name)
        elif action in {"enable", "disable"}:
            self._pool.set_enabled(name, enabled=action == "enable")
        else:
            raise ValueError(f"unsupported backend action: {action}")

        view = next(
            view for view in self.list_backends() if view.name == name
        )
        ADMIN_LOGGER.info(
            json.dumps(
                {
                    "event": "backend_operator_state_changed",
                    "backend": name,
                    "action": action,
                    "enabled": view.enabled,
                    "draining": view.draining,
                },
                separators=(",", ":"),
            )
        )
        return view
