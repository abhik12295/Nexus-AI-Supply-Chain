from __future__ import annotations

import json
import os
import time
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

DEFAULT_BASE_URL = "https://api.tokenfactory.us-central1.nebius.com/v1/"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"


class NemotronConfigurationError(RuntimeError):
    """Raised when Nebius Token Factory credentials are not configured."""


class NemotronResponseError(RuntimeError):
    """Raised when Nemotron returns a response NEXUS cannot validate."""


class IncidentBrief(BaseModel):
    executive_summary: str
    operational_assessment: str
    priority_actions: list[str] = Field(default_factory=list, max_length=5)
    watch_items: list[str] = Field(default_factory=list, max_length=5)
    assumptions: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_used: list[str] = Field(default_factory=list, max_length=8)


class NemotronAnalysisResult(BaseModel):
    brief: IncidentBrief
    model: str
    provider: str = "Nebius Token Factory"
    latency_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class NemotronService:
    """Runtime client for NVIDIA Nemotron on Nebius Token Factory."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("NEBIUS_API_KEY")
        self.base_url = (base_url or os.getenv("NEBIUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.model = model or os.getenv("NEBIUS_MODEL") or DEFAULT_MODEL

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def client(self) -> OpenAI:
        """Return a configured OpenAI-compatible Nebius Token Factory client."""
        if not self.api_key:
            raise NemotronConfigurationError(
                "NEBIUS_API_KEY is not configured. Copy .env.example to .env and add your Token Factory API key."
            )
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def test_connection(self) -> dict[str, Any]:
        """Make a small real inference call to verify auth + model access."""
        started = time.perf_counter()
        completion = self.client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return exactly NEXUS_OK and nothing else."},
                {"role": "user", "content": "Connection test."},
            ],
            temperature=1.0,
            top_p=0.95,
            max_tokens=64,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        content = (completion.choices[0].message.content or "").strip()
        usage = completion.usage
        return {
            "ok": "NEXUS_OK" in content,
            "response": content,
            "model": self.model,
            "finish_reason": completion.choices[0].finish_reason,
            "latency_seconds": round(time.perf_counter() - started, 3),
            "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
            "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
            "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
        }

    def analyze_incident(
        self,
        incident: dict[str, Any],
        analysis: dict[str, Any],
        shipments: list[dict[str, Any]],
        top_n: int = 18,
    ) -> NemotronAnalysisResult:
        context = self._build_context(incident, analysis, shipments, top_n=top_n)

        system_prompt = """You are the NEXUS Incident Analysis Agent, an operational decision-support component.
You receive deterministic incident and shipment-impact facts calculated by software.

Rules:
1. Use ONLY the supplied facts. Never invent closures, delays, costs, capacities, causes, routes, or external events.
2. Do not make a recovery/rerouting decision yet; recovery planning is handled by a later agent.
3. Separate observed/calculated evidence from assumptions.
4. Prioritize operational triage: what matters now, what requires validation, and what should be watched.
5. Do not expose chain-of-thought. Return only the requested final JSON object.
6. Keep each list item concise and operationally useful.

Return valid JSON with exactly these keys:
{
  "executive_summary": "2-4 sentence summary",
  "operational_assessment": "short assessment of exposure and operational significance",
  "priority_actions": ["up to 5 immediate triage actions that do not prescribe a final recovery route"],
  "watch_items": ["up to 5 conditions/data points to monitor"],
  "assumptions": ["up to 5 assumptions or information gaps"],
  "confidence": 0.0,
  "evidence_used": ["up to 8 explicit facts from the supplied context"]
}
"""

        user_prompt = (
            "Analyze this NEXUS incident context. Remember: the numeric exposure values below are authoritative "
            "deterministic outputs and must not be recalculated or altered.\n\n"
            + json.dumps(context, indent=2, default=str)
        )

        started = time.perf_counter()
        completion = self.client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.0,
            top_p=0.95,
            max_tokens=1800,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        latency = round(time.perf_counter() - started, 3)
        raw_content = completion.choices[0].message.content or ""
        payload = self.parse_json(raw_content)

        try:
            brief = IncidentBrief.model_validate(payload)
        except ValidationError as exc:
            raise NemotronResponseError(f"Nemotron JSON did not match the NEXUS schema: {exc}") from exc

        usage = completion.usage
        return NemotronAnalysisResult(
            brief=brief,
            model=self.model,
            latency_seconds=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        )

    @staticmethod
    def _build_context(
        incident: dict[str, Any],
        analysis: dict[str, Any],
        shipments: list[dict[str, Any]],
        top_n: int,
    ) -> dict[str, Any]:
        by_id = {shipment["shipment_id"]: shipment for shipment in shipments}
        exposed = [impact for impact in analysis.get("impacts", []) if impact.get("exposed")]
        exposed.sort(key=lambda row: float(row.get("risk_score", 0)), reverse=True)

        top_shipments: list[dict[str, Any]] = []
        for impact in exposed[:top_n]:
            shipment = by_id.get(impact["shipment_id"])
            if not shipment:
                continue
            top_shipments.append(
                {
                    "shipment_id": shipment["shipment_id"],
                    "route": f'{shipment["origin"]["code"]}->{shipment["destination"]["code"]}',
                    "mode": shipment["mode"],
                    "priority": shipment["priority"],
                    "status": shipment["status"],
                    "eta_ts": shipment["eta_ts"],
                    "risk_score": impact.get("risk_score"),
                    "nearest_distance_km": impact.get("nearest_distance_km"),
                    "exposure_reason": impact.get("exposure_reason"),
                }
            )

        priority_counts = {"critical": 0, "high": 0, "standard": 0}
        mode_counts = {"air": 0, "road": 0, "ocean": 0, "rail": 0}
        for impact in exposed:
            shipment = by_id.get(impact["shipment_id"])
            if not shipment:
                continue
            priority_counts[shipment["priority"]] = priority_counts.get(shipment["priority"], 0) + 1
            mode_counts[shipment["mode"]] = mode_counts.get(shipment["mode"], 0) + 1

        return {
            "incident": {
                "incident_id": incident.get("incident_id"),
                "title": incident.get("title"),
                "incident_type": incident.get("incident_type"),
                "severity": incident.get("severity"),
                "confidence": incident.get("confidence"),
                "radius_km": incident.get("radius_km"),
                "affected_modes": incident.get("affected_modes"),
                "expected_duration_hours": incident.get("expected_duration_hours"),
                "source": incident.get("source"),
                "detected_at": incident.get("detected_at"),
            },
            "deterministic_impact_summary": {
                "total_shipments": analysis.get("total_shipments"),
                "exposed_shipments": analysis.get("exposed_shipments"),
                "critical_exposed": analysis.get("critical_exposed"),
                "exposed_by_priority": priority_counts,
                "exposed_by_mode": mode_counts,
            },
            "highest_risk_exposed_shipments": top_shipments,
        }

    @staticmethod
    def parse_json(raw_content: str) -> dict[str, Any]:
        """Extract the final JSON object even if a reasoning-capable model emits text before it."""
        text = raw_content.strip()

        # Prefer an explicit fenced final answer if present.
        if "```json" in text:
            fenced = text.rsplit("```json", 1)[-1]
            if "```" in fenced:
                fenced = fenced.split("```", 1)[0]
            try:
                payload = json.loads(fenced.strip())
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                pass

        if text.startswith("```"):
            text = text.replace("```json", "", 1).replace("```", "", 1).strip()

        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("root is not an object")
            return payload
        except (json.JSONDecodeError, ValueError):
            # Use the final object-shaped block; planner reasoning may precede it.
            start = text.rfind("\n{")
            if start >= 0:
                start += 1
            else:
                start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(text[start : end + 1])
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    pass

        raise NemotronResponseError(
            "Nemotron returned content that could not be parsed as the required JSON object."
        )
