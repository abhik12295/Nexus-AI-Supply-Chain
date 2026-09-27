from __future__ import annotations

import json
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from services.nemotron_service import NemotronResponseError, NemotronService

EvidenceStatus = Literal["SUPPORTED", "UNVERIFIED", "CONTRADICTED"]
CriticVerdict = Literal["PASS", "CAUTION", "REJECT"]


class EvidenceAssessment(BaseModel):
    claim: str
    status: EvidenceStatus
    explanation: str
    source_ids: list[str] = Field(default_factory=list, max_length=12)


class CriticReview(BaseModel):
    strategy_id: str
    strategy_name: str
    verdict: CriticVerdict
    summary: str
    assessments: list[EvidenceAssessment] = Field(min_length=3, max_length=6)
    critical_issue: str | None = None
    suggested_alternative_strategy_id: str | None = None
    next_action: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_limitations: list[str] = Field(default_factory=list, max_length=5)


class CriticResult(BaseModel):
    review: CriticReview
    model: str
    provider: str = "Nebius Token Factory"
    latency_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class CriticService:
    """Nemotron critic that challenges the simulation leader using bounded public evidence."""

    def __init__(self, runtime: NemotronService | None = None) -> None:
        self.runtime = runtime or NemotronService()

    def review(
        self,
        plan: dict[str, Any],
        simulation: dict[str, Any],
        incident: dict[str, Any],
        incident_brief: dict[str, Any],
        evidence_bundle: dict[str, Any],
    ) -> CriticResult:
        leader_id = str(simulation.get("leader_strategy_id") or "")
        strategies = plan.get("strategies", [])
        leader_strategy = next((row for row in strategies if row.get("strategy_id") == leader_id), None)
        leader_metrics = next((row for row in simulation.get("metrics", []) if row.get("strategy_id") == leader_id), None)
        if not leader_strategy or not leader_metrics:
            raise NemotronResponseError("Stage 5 could not resolve the Stage 4 simulation leader.")

        valid_strategy_ids = {str(row.get("strategy_id")) for row in strategies}
        source_ids = {str(row.get("source_id")) for row in evidence_bundle.get("sources", [])}

        context = {
            "synthetic_scenario_notice": evidence_bundle.get("synthetic_context_note"),
            "incident": {
                "incident_id": incident.get("incident_id"),
                "title": incident.get("title"),
                "severity": incident.get("severity"),
                "confidence": incident.get("confidence"),
                "radius_km": incident.get("radius_km"),
                "affected_modes": incident.get("affected_modes"),
                "expected_duration_hours": incident.get("expected_duration_hours"),
            },
            "prior_incident_brief": incident_brief,
            "simulation_leader": {
                "strategy": leader_strategy,
                "metrics": leader_metrics,
            },
            "alternative_strategies": [
                {
                    "strategy": strategy,
                    "metrics": next(
                        (row for row in simulation.get("metrics", []) if row.get("strategy_id") == strategy.get("strategy_id")),
                        None,
                    ),
                }
                for strategy in strategies
                if strategy.get("strategy_id") != leader_id
            ],
            "simulation_methodology_note": simulation.get("methodology_note"),
            "public_evidence_snapshot": {
                "searched_at_utc": evidence_bundle.get("searched_at_utc"),
                "provider": evidence_bundle.get("provider"),
                "queries": evidence_bundle.get("queries", []),
                "sources": evidence_bundle.get("sources", []),
            },
        }

        system_prompt = """You are the NEXUS Critic Agent. Your job is to challenge the current simulation leader, not to defend it and not to make the final operational decision.

Rules:
1. Treat Stage 4 numeric metrics as deterministic synthetic calculations. Do not recalculate or alter them.
2. Use ONLY the supplied planner assumptions and supplied Tavily evidence snippets/URLs when assessing external assumptions.
3. The incident is synthetic. Live public evidence can challenge alternate-hub assumptions, but must never be presented as proof that the synthetic incident is real.
4. Absence of evidence is UNVERIFIED, never CONTRADICTED.
5. Mark CONTRADICTED only when a supplied source directly conflicts with an essential assumption.
6. Capacity, carrier willingness, contracts, exact handling headroom, and ability to absorb this specific shipment volume remain UNVERIFIED unless a supplied source explicitly supports that exact claim.
7. You may suggest ONE existing Stage 4 alternative for the Stage 6 Decision Agent to inspect, but you must not choose a final recommendation.
8. Cite evidence only by the supplied source IDs (for example E1, E2). Never invent a source ID. Prefer the smallest relevant set of sources, but up to 12 supplied source IDs are allowed when a claim genuinely relies on them.
9. Do not expose chain-of-thought. Return only the final structured assessment.

Verdict guidance:
- PASS: no material contradiction and no critical unresolved assumption blocks consideration.
- CAUTION: one or more material assumptions remain unresolved, or evidence is mixed/insufficient.
- REJECT: supplied evidence directly contradicts an essential assumption required by the leader.

Return a fenced JSON object with exactly this schema:
```json
{
  "strategy_id": "R2",
  "strategy_name": "name",
  "verdict": "PASS|CAUTION|REJECT",
  "summary": "short critic conclusion",
  "assessments": [
    {
      "claim": "assumption or claim being tested",
      "status": "SUPPORTED|UNVERIFIED|CONTRADICTED",
      "explanation": "concise evidence-based explanation",
      "source_ids": ["E1"]
    }
  ],
  "critical_issue": "most important unresolved/contradicted issue or null",
  "suggested_alternative_strategy_id": "existing alternative strategy id or null",
  "next_action": "what Stage 6 should validate or compare next",
  "confidence": 0.0,
  "evidence_limitations": ["up to 5 limitations"]
}
```
"""

        user_prompt = (
            "Challenge the current NEXUS simulation leader using the bounded evidence package below. "
            "Be conservative: if public evidence does not explicitly verify an operational assumption, mark it UNVERIFIED.\n\n"
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
        payload = NemotronService.parse_json(completion.choices[0].message.content or "")

        try:
            review = CriticReview.model_validate(payload)
        except ValidationError as exc:
            raise NemotronResponseError(f"Critic JSON did not match the NEXUS schema: {exc}") from exc

        if review.strategy_id != leader_id:
            raise NemotronResponseError(
                f"Critic reviewed {review.strategy_id!r}, but the current simulation leader is {leader_id!r}."
            )
        if review.suggested_alternative_strategy_id:
            if review.suggested_alternative_strategy_id not in valid_strategy_ids:
                raise NemotronResponseError("Critic suggested a strategy ID outside the Stage 4 plan.")
            if review.suggested_alternative_strategy_id == leader_id:
                raise NemotronResponseError("Critic alternative must not point back to the current leader.")

        for assessment in review.assessments:
            invalid = set(assessment.source_ids) - source_ids
            if invalid:
                raise NemotronResponseError(
                    f"Critic cited unknown evidence IDs: {sorted(invalid)}."
                )
            if assessment.status == "UNVERIFIED" and not assessment.source_ids:
                continue

        if not evidence_bundle.get("sources") and review.verdict == "PASS":
            review.verdict = "CAUTION"
            review.evidence_limitations.append("No public evidence sources were returned; a PASS verdict is not allowed.")

        usage = completion.usage
        return CriticResult(
            review=review,
            model=self.runtime.model,
            latency_seconds=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        )
