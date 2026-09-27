from __future__ import annotations

import json
import math
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from services.nemotron_service import NemotronResponseError, NemotronService

StrategyType = Literal["hold_monitor", "reroute_all", "protect_priority"]


class RecoveryStrategy(BaseModel):
    strategy_id: str
    name: str
    strategy_type: StrategyType
    routing_hub: str | None = None
    description: str
    rationale: str
    assumptions: list[str] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def validate_hub_requirement(self):
        if self.strategy_type == "hold_monitor" and self.routing_hub is not None:
            raise ValueError("hold_monitor must not specify routing_hub")
        if self.strategy_type in {"reroute_all", "protect_priority"} and not self.routing_hub:
            raise ValueError(f"{self.strategy_type} requires routing_hub")
        return self


class RecoveryPlan(BaseModel):
    planning_summary: str
    strategies: list[RecoveryStrategy] = Field(min_length=3, max_length=3)
    planning_assumptions: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_strategy_mix(self):
        kinds = [item.strategy_type for item in self.strategies]
        if set(kinds) != {"hold_monitor", "reroute_all", "protect_priority"}:
            raise ValueError(
                "plan must contain exactly one hold_monitor, one reroute_all, and one protect_priority strategy"
            )
        ids = [item.strategy_id for item in self.strategies]
        if len(ids) != len(set(ids)):
            raise ValueError("strategy_id values must be unique")
        return self


class RecoveryPlannerResult(BaseModel):
    plan: RecoveryPlan
    model: str
    provider: str = "Nebius Token Factory"
    latency_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class RecoveryPlanner:
    """Nemotron planner that proposes bounded scenario structures; it never calculates outcome metrics."""

    def __init__(self, runtime: NemotronService | None = None) -> None:
        self.runtime = runtime or NemotronService()

    def plan(
        self,
        incident: dict[str, Any],
        analysis: dict[str, Any],
        shipments: list[dict[str, Any]],
        incident_brief: dict[str, Any],
    ) -> RecoveryPlannerResult:
        candidates = self._candidate_hubs(incident, shipments)
        if len(candidates) < 2:
            raise NemotronResponseError("NEXUS could not identify at least two alternate synthetic hubs for planning.")

        context = self._planning_context(incident, analysis, shipments, incident_brief, candidates)
        allowed_codes = [hub["code"] for hub in candidates]

        system_prompt = f"""You are the NEXUS Recovery Planner.
Your job is to propose THREE bounded recovery scenarios for a synthetic supply-chain incident.

Critical rules:
1. Use ONLY the supplied incident, impact, shipment, and prior-analysis facts.
2. NEVER invent or estimate cost, delay, risk, SLA impact, capacity, congestion, closure status, or probability. A deterministic simulator calculates all outcome metrics after you finish.
3. You may reference a routing hub ONLY from this allowed list: {allowed_codes}.
4. Return exactly these three strategy types, one each:
   - hold_monitor: maintain current paths while monitoring the disruption. routing_hub MUST be null.
   - reroute_all: reroute all exposed shipments through one allowed alternate hub.
   - protect_priority: reroute only critical/high exposed shipments through a DIFFERENT allowed alternate hub; standard-priority exposed shipments remain on current paths.
5. The two intervention strategies must use different routing hubs.
6. Treat every route as a scenario proposal only. Do not claim the alternate hub has capacity or is operationally available; those remain assumptions to verify.
7. Do NOT state shipment counts in the strategy name, description, or rationale. The deterministic simulator is the sole source of truth for which shipments and how many shipments are targeted.
8. For protect_priority, describe the scope only as Critical + High exposed shipments; never describe it as Critical-only.
9. Do not expose chain-of-thought. Your FINAL answer must be a fenced JSON object and nothing after it.

Final JSON schema:
```json
{{
  "planning_summary": "short description of the scenario set",
  "strategies": [
    {{
      "strategy_id": "R1",
      "name": "short scenario name",
      "strategy_type": "hold_monitor|reroute_all|protect_priority",
      "routing_hub": null,
      "description": "what this scenario changes",
      "rationale": "why this is useful to simulate using supplied evidence only",
      "assumptions": ["up to 4 information gaps that must be validated"]
    }}
  ],
  "planning_assumptions": ["up to 5 plan-level information gaps"]
}}
```
"""

        user_prompt = (
            "Create the three required NEXUS recovery scenarios. Do not calculate any outcome metrics. "
            "The next software component will simulate every scenario deterministically.\n\n"
            + json.dumps(context, indent=2, default=str)
        )

        started = time.perf_counter()
        completion = self.runtime.client().chat.completions.create(
            model=self.runtime.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.0,
            top_p=0.95,
            max_tokens=5000,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": True,
                    "low_effort": True,
                }
            },
        )
        latency = round(time.perf_counter() - started, 3)
        raw_content = completion.choices[0].message.content or ""
        payload = NemotronService.parse_json(raw_content)

        try:
            plan = RecoveryPlan.model_validate(payload)
        except ValidationError as exc:
            raise NemotronResponseError(f"Recovery-plan JSON did not match the NEXUS schema: {exc}") from exc

        self._validate_allowed_hubs(plan, allowed_codes)

        usage = completion.usage
        return RecoveryPlannerResult(
            plan=plan,
            model=self.runtime.model,
            latency_seconds=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        )

    @staticmethod
    def _validate_allowed_hubs(plan: RecoveryPlan, allowed_codes: list[str]) -> None:
        intervention_hubs: list[str] = []
        for strategy in plan.strategies:
            if strategy.routing_hub:
                if strategy.routing_hub not in allowed_codes:
                    raise NemotronResponseError(
                        f"Planner selected hub {strategy.routing_hub!r}, which is outside the bounded candidate set."
                    )
                intervention_hubs.append(strategy.routing_hub)
        if len(intervention_hubs) != len(set(intervention_hubs)):
            raise NemotronResponseError("Planner must use different hubs for the two intervention strategies.")

    @classmethod
    def _candidate_hubs(cls, incident: dict[str, Any], shipments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hubs: dict[str, dict[str, Any]] = {}
        for shipment in shipments:
            hubs[shipment["origin"]["code"]] = shipment["origin"]
            hubs[shipment["destination"]["code"]] = shipment["destination"]

        ranked: list[dict[str, Any]] = []
        for hub in hubs.values():
            distance = cls._haversine_km(
                float(incident["lat"]),
                float(incident["lon"]),
                float(hub["lat"]),
                float(hub["lon"]),
            )
            # Exclude the incident location/radius itself; alternate nodes must sit outside the seeded impact radius.
            if distance <= float(incident.get("radius_km", 0)):
                continue
            ranked.append(
                {
                    "code": hub["code"],
                    "city": hub["city"],
                    "country": hub["country"],
                    "lat": hub["lat"],
                    "lon": hub["lon"],
                    "distance_from_incident_km": round(distance, 1),
                }
            )

        ranked.sort(key=lambda row: row["distance_from_incident_km"])
        return ranked[:5]

    @classmethod
    def _planning_context(
        cls,
        incident: dict[str, Any],
        analysis: dict[str, Any],
        shipments: list[dict[str, Any]],
        incident_brief: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_id = {shipment["shipment_id"]: shipment for shipment in shipments}
        exposed = [impact for impact in analysis.get("impacts", []) if impact.get("exposed")]
        exposed.sort(key=lambda row: float(row.get("risk_score", 0)), reverse=True)

        top_exposures = []
        for impact in exposed[:12]:
            shipment = by_id.get(impact["shipment_id"])
            if not shipment:
                continue
            top_exposures.append(
                {
                    "shipment_id": shipment["shipment_id"],
                    "route": f'{shipment["origin"]["code"]}->{shipment["destination"]["code"]}',
                    "mode": shipment["mode"],
                    "priority": shipment["priority"],
                    "risk_score": impact.get("risk_score"),
                    "exposure_reason": impact.get("exposure_reason"),
                }
            )

        return {
            "incident": {
                "incident_id": incident.get("incident_id"),
                "title": incident.get("title"),
                "severity": incident.get("severity"),
                "confidence": incident.get("confidence"),
                "affected_modes": incident.get("affected_modes"),
                "expected_duration_hours": incident.get("expected_duration_hours"),
                "radius_km": incident.get("radius_km"),
            },
            "deterministic_impact": {
                "total_shipments": analysis.get("total_shipments"),
                "exposed_shipments": analysis.get("exposed_shipments"),
                "critical_exposed": analysis.get("critical_exposed"),
            },
            "prior_nemotron_brief": incident_brief,
            "nearest_allowed_alternate_hubs": candidates,
            "highest_risk_exposures": top_exposures,
            "scenario_contract": {
                "metrics_are_calculated_later": True,
                "capacity_and_live_hub_availability_are_unknown": True,
                "allowed_strategy_types": ["hold_monitor", "reroute_all", "protect_priority"],
                "authoritative_target_scope": {
                    "hold_monitor": "no rerouting",
                    "reroute_all": "all exposed shipments",
                    "protect_priority": "critical + high exposed shipments",
                },
                "planner_must_not_state_target_counts": True,
            },
        }

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0088
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return 2 * radius * math.asin(math.sqrt(a))
