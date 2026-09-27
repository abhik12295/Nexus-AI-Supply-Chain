from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_API_URL = "http://127.0.0.1:8000"


class NexusAPIError(RuntimeError):
    """Raised when the Streamlit command center cannot reach the NEXUS API."""


class NexusAPI:
    def __init__(self, base_url: str | None = None, timeout: int = 15) -> None:
        self.base_url = (base_url or os.getenv("NEXUS_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise NexusAPIError(
                f"Unable to reach NEXUS API at {url}. Make sure FastAPI is running on port 8000."
            ) from exc

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def shipments(self, limit: int = 1200) -> list[dict[str, Any]]:
        return self._get("/api/shipments", params={"limit": limit})

    def incidents(self) -> list[dict[str, Any]]:
        return self._get("/api/incidents")

    def incident_analysis(self, incident_id: str) -> dict[str, Any]:
        return self._get(f"/api/incidents/{incident_id}/analysis")
