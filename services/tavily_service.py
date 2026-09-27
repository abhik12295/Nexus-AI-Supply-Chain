from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import BaseModel, Field

DEFAULT_TAVILY_BASE_URL = "https://api.tavily.com"


class TavilyConfigurationError(RuntimeError):
    """Raised when the Tavily API key is not configured."""


class TavilySearchError(RuntimeError):
    """Raised when the Tavily Search API request fails."""


class EvidenceSource(BaseModel):
    source_id: str
    query_kind: str
    title: str
    url: str
    content: str
    score: float | None = None


class EvidenceQuery(BaseModel):
    query_kind: str
    query: str
    result_count: int = Field(ge=0)
    source_ids: list[str] = Field(default_factory=list)


class EvidenceBundle(BaseModel):
    strategy_id: str
    strategy_name: str
    routing_hub: str | None = None
    provider: str = "Tavily Search API"
    searched_at_utc: str
    search_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    latency_seconds: float = Field(ge=0.0)
    queries: list[EvidenceQuery] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    synthetic_context_note: str


class TavilyEvidenceService:
    """Small evidence layer that retrieves current public web snippets for the Critic Agent."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.base_url = (base_url or os.getenv("TAVILY_BASE_URL") or DEFAULT_TAVILY_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def test_connection(self) -> dict[str, Any]:
        if not self.api_key:
            raise TavilyConfigurationError(
                "TAVILY_API_KEY is not configured. Add your Tavily key to .env before running Stage 5."
            )
        started = time.perf_counter()
        response = self._search(
            query="FAA airport operational status Atlanta ATL",
            search_depth="basic",
            max_results=1,
        )
        results = response.get("results") or []
        return {
            "ok": bool(results),
            "result_count": len(results),
            "latency_seconds": round(time.perf_counter() - started, 3),
            "first_title": results[0].get("title") if results else None,
            "first_url": results[0].get("url") if results else None,
        }

    def collect_for_strategy(
        self,
        strategy: dict[str, Any],
        incident: dict[str, Any],
        shipments: list[dict[str, Any]],
    ) -> EvidenceBundle:
        if not self.api_key:
            raise TavilyConfigurationError(
                "TAVILY_API_KEY is not configured. Add your Tavily key to .env before running the Critic Agent."
            )

        hub_index = self._hub_index(shipments)
        routing_hub = strategy.get("routing_hub")
        hub = hub_index.get(routing_hub) if routing_hub else None
        queries = self._build_queries(strategy, incident, hub)

        started = time.perf_counter()
        evidence_queries: list[EvidenceQuery] = []
        evidence_sources: list[EvidenceSource] = []
        seen_urls: set[str] = set()

        for query_kind, query in queries:
            payload = self._search(
                query=query,
                search_depth="basic",
                max_results=4,
            )
            source_ids: list[str] = []
            for row in payload.get("results") or []:
                url = str(row.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                source_id = f"E{len(evidence_sources) + 1}"
                source_ids.append(source_id)
                evidence_sources.append(
                    EvidenceSource(
                        source_id=source_id,
                        query_kind=query_kind,
                        title=str(row.get("title") or "Untitled source").strip(),
                        url=url,
                        content=str(row.get("content") or "").strip()[:1200],
                        score=float(row["score"]) if row.get("score") is not None else None,
                    )
                )
            evidence_queries.append(
                EvidenceQuery(
                    query_kind=query_kind,
                    query=query,
                    result_count=len(source_ids),
                    source_ids=source_ids,
                )
            )

        return EvidenceBundle(
            strategy_id=str(strategy.get("strategy_id") or "UNKNOWN"),
            strategy_name=str(strategy.get("name") or "Unnamed strategy"),
            routing_hub=routing_hub,
            searched_at_utc=datetime.now(timezone.utc).isoformat(),
            search_count=len(queries),
            source_count=len(evidence_sources),
            latency_seconds=round(time.perf_counter() - started, 3),
            queries=evidence_queries,
            sources=evidence_sources,
            synthetic_context_note=(
                "The NEXUS incident and shipment network are synthetic. Tavily results are a live public evidence "
                "snapshot used only to challenge assumptions about an alternate hub or surrounding operating context; "
                "they do not prove that the synthetic incident itself is real."
            ),
        )

    def _search(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 4,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise TavilyConfigurationError("TAVILY_API_KEY is not configured.")

        url = f"{self.base_url}/search"
        payload = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            suffix = f" (HTTP {status})" if status else ""
            raise TavilySearchError(f"Tavily search failed{suffix}: {exc}") from exc
        except ValueError as exc:
            raise TavilySearchError("Tavily returned a non-JSON response.") from exc

        if not isinstance(data, dict):
            raise TavilySearchError("Tavily returned an unexpected response shape.")
        return data

    @staticmethod
    def _hub_index(shipments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        hubs: dict[str, dict[str, Any]] = {}
        for shipment in shipments:
            hubs[shipment["origin"]["code"]] = shipment["origin"]
            hubs[shipment["destination"]["code"]] = shipment["destination"]
        return hubs

    @staticmethod
    def _build_queries(
        strategy: dict[str, Any],
        incident: dict[str, Any],
        hub: dict[str, Any] | None,
    ) -> list[tuple[str, str]]:
        affected_modes = {str(mode).lower() for mode in incident.get("affected_modes", [])}
        if hub:
            code = hub.get("code", strategy.get("routing_hub") or "")
            city = hub.get("city", code)
            country = hub.get("country", "")
            queries: list[tuple[str, str]] = [
                (
                    "hub_operations",
                    f"{code} {city} airport current operational status delays closures official",
                ),
                (
                    "weather",
                    f"{city} {country} current severe weather alerts airport operations",
                ),
            ]
            if "road" in affected_modes:
                queries.append(
                    (
                        "surface_access",
                        f"{city} current road closures traffic disruption airport access transportation",
                    )
                )
            return queries

        title = str(incident.get("title") or "current disruption")
        return [
            ("incident_status", f"{title} current operational status official"),
            ("weather", f"{title} current weather alerts"),
        ]
