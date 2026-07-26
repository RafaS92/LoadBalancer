"""HTTPX implementation of the backend health-probe port."""

from __future__ import annotations

import httpx

from load_balancer.domain.models import Backend


class HttpHealthProbe:
    """Probe one backend with a reusable HTTPX client."""

    def __init__(
        self,
        *,
        timeout: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None

    def probe(self, backend: Backend, path: str) -> bool:
        try:
            response = self._client.get(f"{backend.url.rstrip('/')}{path}")
            return response.is_success
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
