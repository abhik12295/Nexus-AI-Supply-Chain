from __future__ import annotations

import os
from typing import Any

import requests

from app.data import generate_shipments, seeded_incident
from app.impact import analyze_incident

DEFAULT_API_URL = "embedded"

# A single deterministic in-process dataset lets Streamlit Community Cloud
# run the command center without a separate localhost FastAPI process.
_LOCAL_SHIPMENTS = generate_shipments()
_LOCAL_INCIDENT = seeded_incident()
_LOCAL_INCIDENTS = {_LOCAL_INCIDENT.incident_id: _LOCAL_INCIDENT}


class NexusAPIError(RuntimeError):
    """Raised when the NEXUS data/runtime layer cannot serve a request."""


class NexusAPI:
    """
    NEXUS data client.

    Use "embedded" (the default) for Streamlit Community Cloud.
    Supply an http(s) FastAPI URL for local/API-backed deployments.
    """

    def __init__(self, base_url: str | None = None, timeout: int = 15) -> None:
        configured = base_url or os.getenv("NEXUS_API_URL") or DEFAULT_API_URL
        self.base_url = configured.rstrip("/")
        self.timeout = timeout

    @property
    def embedded(self) -> bool:
        return self.base_url.lower() in {"embedded", "local", "inprocess", "in-process"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self.embedded:
            return self._embedded_get(path, params or {})

        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise NexusAPIError(
                f"Unable to reach NEXUS API at {url}. "
                "Use NEXUS_API_URL=embedded on Streamlit Community Cloud."
            ) from exc

    def _embedded_get(self, path: str, params: dict[str, Any]) -> Any:
        if path == "/health":
            return {
                "status": "ok",
                "service": "nexus-embedded-runtime",
                "mode": "embedded",
            }

        if path == "/api/shipments":
            limit = max(1, int(params.get("limit", 1200)))
            return [
                shipment.model_dump(mode="json")
                for shipment in _LOCAL_SHIPMENTS[:limit]
            ]

        if path == "/api/incidents":
            return [
                incident.model_dump(mode="json")
                for incident in _LOCAL_INCIDENTS.values()
            ]

        if path.startswith("/api/incidents/") and path.endswith("/analysis"):
            incident_id = (
                path.removeprefix("/api/incidents/")
                .removesuffix("/analysis")
            )
            incident = _LOCAL_INCIDENTS.get(incident_id)
            if not incident:
                raise NexusAPIError(f"Incident not found: {incident_id}")

            result = analyze_incident(incident, _LOCAL_SHIPMENTS)
            return result.model_dump(mode="json")

        raise NexusAPIError(f"Unsupported embedded NEXUS path: {path}")

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def shipments(self, limit: int = 1200) -> list[dict[str, Any]]:
        return self._get("/api/shipments", params={"limit": limit})

    def incidents(self) -> list[dict[str, Any]]:
        return self._get("/api/incidents")

    def incident_analysis(self, incident_id: str) -> dict[str, Any]:
        return self._get(f"/api/incidents/{incident_id}/analysis")
