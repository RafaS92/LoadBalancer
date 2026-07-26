"""Backend administration use cases."""

from __future__ import annotations

from dataclasses import dataclass

from load_balancer.domain.models import BackendStatus
from load_balancer.domain.routing import BackendPool
from load_balancer.ports.events import (
    BackendOperatorStateChanged,
    EventSink,
    NullEventSink,
)


@dataclass(frozen=True, slots=True)
class BackendView:
    """Stable application representation of one backend."""

    name: str
    url: str
    healthy: bool
    enabled: bool
    draining: bool
    drained: bool
    active_requests: int

    @classmethod
    def from_status(cls, status: BackendStatus) -> BackendView:
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
        state: dict[str, object] = {
            "healthy": self.healthy,
            "enabled": self.enabled,
            "draining": self.draining,
            "drained": self.drained,
            "active_requests": self.active_requests,
        }
        if include_url:
            return {"name": self.name, "url": self.url, **state}
        return {"name": self.name, **state}


class ControlPlaneService:
    """List backend state and apply operator decisions."""

    def __init__(
        self,
        pool: BackendPool,
        events: EventSink | None = None,
    ) -> None:
        self._pool = pool
        self._events = events or NullEventSink()

    def list_backends(self) -> tuple[BackendView, ...]:
        return tuple(
            BackendView.from_status(status) for status in self._pool.snapshot()
        )

    def apply_backend_action(self, name: str, action: str) -> BackendView:
        if action == "drain":
            self._pool.begin_drain(name)
        elif action in {"enable", "disable"}:
            self._pool.set_enabled(name, enabled=action == "enable")
        else:
            raise ValueError(f"unsupported backend action: {action}")

        view = next(
            view for view in self.list_backends() if view.name == name
        )
        self._events.publish(
            BackendOperatorStateChanged(
                backend_name=name,
                action=action,
                enabled=view.enabled,
                draining=view.draining,
            )
        )
        return view
