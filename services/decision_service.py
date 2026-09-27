from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from services.nemotron_service import NemotronResponseError, NemotronService

DecisionStatus = Literal["READY_FOR_HUMAN_APPROVAL", "HOLD_FOR_HUMAN_VALIDATION"]


class DecisionRecommendation(BaseModel):
    decision_status: DecisionStatus
    selected_strategy_id: str | None = None
    headline: str
    summary: str
    rationale: list[str] = Field(default_factory=list, min_length=2, max_length=6)
    operator_actions: list[str] = Field(default_factory=list, min_length=2, max_length=6)
    blocking_items: list[str] = Field(default_factory=list, max_length=6)
    human_validation_requirements: list[str] = Field(default_factory=list, max_length=6)
    evidence_source_ids: list[str] = Field(default_factory=list, max_length=12)
    alternative_strategy_ids: list[str] = Field(default_factory=list, max_length=2)
    confidence: float = Field(ge=0.0, le=1.0)


class DecisionPolicyGate(BaseModel):
    must_hold: bool
    reasons: list[str] = Field(default_factory=list)
    evidence_age_minutes: float | None = None
    evidence_stale: bool = False
    critic_verdict: str
    critic_has_critical_issue: bool
    contradicted_claim_count: int
    unverified_claim_count: int


class DecisionResult(BaseModel):
    decision: DecisionRecommendation
    policy_gate: DecisionPolicyGate
    model: str
    provider: str = "Nebius Token Factory"
    latency_seconds: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    evidence_reused: bool = True
    tavily_searches_this_stage: int = 0


class DecisionService:
    """Stage 6 final-decision agent with a deterministic safety/approval policy gate."""

    EVIDENCE_MAX_AGE_MINUTES = 30.0

    def __init__(self, runtime: NemotronService | None = None) -> None:
        self.runtime = runtime or NemotronService()

    def decide(
        self,
        plan: dict[str, Any],
        simulation: dict[str, Any],
        critic_result: dict[str, Any],
        evidence_bundle: dict[str, Any],
        incident_brief: dict[str, Any],
    ) -> DecisionResult:
        strategies = plan.get("strategies", [])
        metrics = simulation.get("metrics", [])
        valid_strategy_ids = {str(row.get("strategy_id")) for row in strategies}
        evidence_source_ids = {
            str(row.get("source_id"))
            for row in evidence_bundle.get("sources", [])
            if row.get("source_id")
        }

        if not valid_strategy_ids:
            raise NemotronResponseError("Stage 6 requires the Stage 4 strategy set.")
        if not metrics:
            raise NemotronResponseError("Stage 6 requires deterministic Stage 4 simulation metrics.")

        review = critic_result.get("review", {})
        gate = self.evaluate_policy_gate(review=review, evidence_bundle=evidence_bundle)

        context = {
            "decision_contract": {
                "human_is_final_authority": True,
                "no_real_world_action_execution": True,
                "tavily_searches_this_stage": 0,
                "stage_5_evidence_is_reused": True,
                "deterministic_policy_gate": gate.model_dump(),
            },
            "prior_incident_brief": incident_brief,
            "stage_4": {
                "simulation_leader_strategy_id": simulation.get("leader_strategy_id"),
                "simulation_leader_name": simulation.get("leader_name"),
                "weights": simulation.get("weights"),
                "strategies": strategies,
                "metrics": metrics,
                "methodology_note": simulation.get("methodology_note"),
            },
            "stage_5": {
                "critic_review": review,
                "evidence_snapshot": {
                    "searched_at_utc": evidence_bundle.get("searched_at_utc"),
                    "provider": evidence_bundle.get("provider"),
                    "search_count": evidence_bundle.get("search_count"),
                    "source_count": evidence_bundle.get("source_count"),
                    "sources": evidence_bundle.get("sources", []),
                    "synthetic_context_note": evidence_bundle.get("synthetic_context_note"),
                },
            },
        }

        hold_instruction = (
            "The deterministic policy gate says MUST HOLD. You MUST return decision_status "
            "HOLD_FOR_HUMAN_VALIDATION and selected_strategy_id must be null. "
            if gate.must_hold
            else
            "The deterministic policy gate does not force a hold. You may select exactly one existing "
            "strategy for human approval if the supplied evidence supports doing so; otherwise choose HOLD_FOR_HUMAN_VALIDATION. "
        )

        system_prompt = f"""You are the NEXUS Stage 6 Decision Agent.
You synthesize deterministic simulation results, the Stage 5 Critic review, and the existing Tavily evidence snapshot.
You do NOT execute logistics actions. A human operator remains the final authority.

Hard rules:
1. Stage 4 numeric metrics are deterministic synthetic calculations. Never alter or recalculate them.
2. Use ONLY the supplied Stage 5 evidence. Do not claim you performed a new web search.
3. Stage 6 performs ZERO Tavily searches by default. Do not invent new evidence.
4. Exact spare capacity, carrier willingness, handling slots, contracts, and ability to absorb the precise shipment volume remain unresolved unless Stage 5 explicitly verified them.
5. A strategy named as an alternative by the Critic is only a candidate for review unless evidence supports it; do not silently promote it to a final selection.
6. If decision_status is READY_FOR_HUMAN_APPROVAL, selected_strategy_id must be one of the supplied Stage 4 strategies.
7. If decision_status is HOLD_FOR_HUMAN_VALIDATION, selected_strategy_id must be null.
8. Never claim that the synthetic incident is a real event.
9. Do not expose chain-of-thought. Return only the final structured result.
10. {hold_instruction}

Return a fenced JSON object with exactly this schema:
```json
{{
  "decision_status": "READY_FOR_HUMAN_APPROVAL|HOLD_FOR_HUMAN_VALIDATION",
  "selected_strategy_id": "R1|R2|R3|null",
  "headline": "short decision headline",
  "summary": "concise evidence-backed conclusion",
  "rationale": ["2 to 6 concise reasons"],
  "operator_actions": ["2 to 6 next operational steps"],
  "blocking_items": ["unresolved blockers, if any"],
  "human_validation_requirements": ["specific items a human must verify"],
  "evidence_source_ids": ["E1"],
  "alternative_strategy_ids": ["R3"],
  "confidence": 0.0
}}
```
"""

        user_prompt = (
            "Produce the Stage 6 NEXUS decision. Respect the deterministic policy gate and preserve human approval.\n\n"
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
            max_tokens=4500,
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
            decision = DecisionRecommendation.model_validate(payload)
        except ValidationError as exc:
            raise NemotronResponseError(f"Stage 6 decision JSON did not match the NEXUS schema: {exc}") from exc

        # Validate model references before applying deterministic policy.
        if decision.selected_strategy_id and decision.selected_strategy_id not in valid_strategy_ids:
            raise NemotronResponseError("Decision Agent selected a strategy outside the Stage 4 strategy set.")

        invalid_alternatives = set(decision.alternative_strategy_ids) - valid_strategy_ids
        if invalid_alternatives:
            raise NemotronResponseError(
                f"Decision Agent referenced unknown alternative strategy IDs: {sorted(invalid_alternatives)}."
            )

        invalid_sources = set(decision.evidence_source_ids) - evidence_source_ids
        if invalid_sources:
            raise NemotronResponseError(
                f"Decision Agent cited unknown Stage 5 evidence IDs: {sorted(invalid_sources)}."
            )

        # Deterministic guardrail always wins over the model.
        if gate.must_hold:
            decision.decision_status = "HOLD_FOR_HUMAN_VALIDATION"
            decision.selected_strategy_id = None
            decision.blocking_items = self._merge_unique(decision.blocking_items, gate.reasons, limit=6)
            if not decision.human_validation_requirements:
                decision.human_validation_requirements = gate.reasons[:6]

        if decision.decision_status == "HOLD_FOR_HUMAN_VALIDATION":
            decision.selected_strategy_id = None
        elif not decision.selected_strategy_id:
            raise NemotronResponseError(
                "READY_FOR_HUMAN_APPROVAL requires a selected Stage 4 strategy ID."
            )

        usage = completion.usage
        return DecisionResult(
            decision=decision,
            policy_gate=gate,
            model=self.runtime.model,
            latency_seconds=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        )

    @classmethod
    def evaluate_policy_gate(
        cls,
        review: dict[str, Any],
        evidence_bundle: dict[str, Any],
        now: datetime | None = None,
    ) -> DecisionPolicyGate:
        verdict = str(review.get("verdict") or "CAUTION").upper()
        assessments = review.get("assessments", []) or []
        contradicted = sum(
            1 for row in assessments if str(row.get("status", "")).upper() == "CONTRADICTED"
        )
        unverified = sum(
            1 for row in assessments if str(row.get("status", "")).upper() == "UNVERIFIED"
        )
        critical_issue = bool(str(review.get("critical_issue") or "").strip())

        age_minutes: float | None = None
        stale = False
        searched_at = evidence_bundle.get("searched_at_utc")
        if searched_at:
            try:
                searched_dt = datetime.fromisoformat(str(searched_at).replace("Z", "+00:00"))
                if searched_dt.tzinfo is None:
                    searched_dt = searched_dt.replace(tzinfo=timezone.utc)
                now_dt = now or datetime.now(timezone.utc)
                age_minutes = max(0.0, (now_dt - searched_dt).total_seconds() / 60.0)
                stale = age_minutes > cls.EVIDENCE_MAX_AGE_MINUTES
            except Exception:
                stale = True

        reasons: list[str] = []
        source_count = int(evidence_bundle.get("source_count") or len(evidence_bundle.get("sources", []) or []))
        if verdict == "REJECT":
            reasons.append("Stage 5 Critic rejected the simulation leader.")
        if contradicted:
            reasons.append(f"{contradicted} material assumption(s) are contradicted by supplied evidence.")
        if critical_issue:
            reasons.append(str(review.get("critical_issue")).strip())
        if source_count == 0:
            reasons.append("No public evidence sources are available for the final decision.")
        if stale:
            reasons.append(
                f"Stage 5 public evidence is older than {cls.EVIDENCE_MAX_AGE_MINUTES:.0f} minutes; refresh the challenge review."
            )

        # A CAUTION verdict with a named critical issue is deliberately non-executable.
        must_hold = bool(reasons) or (verdict == "CAUTION" and critical_issue)

        return DecisionPolicyGate(
            must_hold=must_hold,
            reasons=cls._merge_unique([], reasons, limit=8),
            evidence_age_minutes=round(age_minutes, 1) if age_minutes is not None else None,
            evidence_stale=stale,
            critic_verdict=verdict,
            critic_has_critical_issue=critical_issue,
            contradicted_claim_count=contradicted,
            unverified_claim_count=unverified,
        )

    @staticmethod
    def _merge_unique(existing: list[str], additions: list[str], limit: int) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*existing, *additions]:
            value = str(item).strip()
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                merged.append(value)
            if len(merged) >= limit:
                break
        return merged
