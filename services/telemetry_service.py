from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class RuntimeTelemetry(BaseModel):
    core_stages_complete: int = Field(ge=0, le=6)
    nemotron_calls: int = Field(ge=0)
    tavily_searches: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_model_latency_seconds: float = Field(ge=0)
    evidence_latency_seconds: float = Field(ge=0)
    evidence_age_minutes: float | None = None
    decision_status: str
    critic_verdict: str
    policy_gate: str
    stage7_nemotron_calls: int = 0
    stage7_tavily_searches: int = 0


class ReadinessCheck(BaseModel):
    key: str
    label: str
    status: str
    detail: str


class ReadinessReport(BaseModel):
    checks: list[ReadinessCheck]
    ready_count: int
    total_count: int
    overall_status: str


class TelemetryService:
    """Purely derives runtime and readiness metadata from already-computed NEXUS state."""

    def summarize(
        self,
        *,
        ai_result: dict[str, Any] | None,
        planner_result: dict[str, Any] | None,
        evidence_result: dict[str, Any] | None,
        critic_result: dict[str, Any] | None,
        decision_result: dict[str, Any] | None,
    ) -> RuntimeTelemetry:
        model_results = [
            ai_result,
            planner_result,
            critic_result,
            decision_result,
        ]
        nemotron_calls = sum(1 for row in model_results if row)
        total_tokens = sum(int((row or {}).get("total_tokens") or 0) for row in model_results)
        total_latency = sum(float((row or {}).get("latency_seconds") or 0) for row in model_results)

        tavily_searches = int((evidence_result or {}).get("search_count") or 0)
        evidence_latency = float((evidence_result or {}).get("latency_seconds") or 0)

        evidence_age = None
        searched_at = (evidence_result or {}).get("searched_at_utc")
        if searched_at:
            try:
                searched_dt = datetime.fromisoformat(str(searched_at).replace("Z", "+00:00"))
                if searched_dt.tzinfo is None:
                    searched_dt = searched_dt.replace(tzinfo=timezone.utc)
                evidence_age = max(
                    0.0,
                    (datetime.now(timezone.utc) - searched_dt).total_seconds() / 60.0,
                )
            except Exception:
                evidence_age = None

        complete = sum(
            bool(row)
            for row in [
                True,  # DETECT is present whenever app data loaded
                True,  # IMPACT is present whenever app data loaded
                ai_result,
                planner_result,
                critic_result,
                decision_result,
            ]
        )

        decision = (decision_result or {}).get("decision", {})
        gate = (decision_result or {}).get("policy_gate", {})
        review = (critic_result or {}).get("review", {})

        return RuntimeTelemetry(
            core_stages_complete=min(6, complete),
            nemotron_calls=nemotron_calls,
            tavily_searches=tavily_searches,
            total_tokens=total_tokens,
            total_model_latency_seconds=round(total_latency, 3),
            evidence_latency_seconds=round(evidence_latency, 3),
            evidence_age_minutes=round(evidence_age, 1) if evidence_age is not None else None,
            decision_status=str(decision.get("decision_status", "NOT_RUN")),
            critic_verdict=str(review.get("verdict", "NOT_RUN")),
            policy_gate="HOLD ENFORCED" if gate.get("must_hold") else ("CLEARED" if decision_result else "NOT_RUN"),
        )

    def readiness(
        self,
        *,
        backend_health: dict[str, Any] | None,
        nemotron_configured: bool,
        tavily_configured: bool,
        telemetry: RuntimeTelemetry,
        decision_result: dict[str, Any] | None,
    ) -> ReadinessReport:
        evidence_fresh = (
            telemetry.evidence_age_minutes is not None
            and telemetry.evidence_age_minutes <= 30
        )

        checks = [
            ReadinessCheck(
                key="backend",
                label="FastAPI backend",
                status="READY" if backend_health else "CHECK",
                detail="Health endpoint reachable" if backend_health else "Backend health unavailable",
            ),
            ReadinessCheck(
                key="nemotron",
                label="Nebius / Nemotron",
                status="READY" if nemotron_configured else "CHECK",
                detail="Inference runtime configured" if nemotron_configured else "NEBIUS_API_KEY not configured",
            ),
            ReadinessCheck(
                key="tavily",
                label="Tavily evidence",
                status="READY" if tavily_configured else "CHECK",
                detail="Evidence search configured" if tavily_configured else "TAVILY_API_KEY not configured",
            ),
            ReadinessCheck(
                key="core_loop",
                label="Core NEXUS loop",
                status="READY" if telemetry.core_stages_complete == 6 else "CHECK",
                detail=f"{telemetry.core_stages_complete}/6 core stages complete",
            ),
            ReadinessCheck(
                key="evidence",
                label="Evidence freshness",
                status="READY" if evidence_fresh else "CHECK",
                detail=(
                    f"Stage 5 snapshot age: {telemetry.evidence_age_minutes:.1f} min"
                    if telemetry.evidence_age_minutes is not None
                    else "No evidence snapshot yet"
                ),
            ),
            ReadinessCheck(
                key="guardrail",
                label="Deterministic policy gate",
                status="READY" if decision_result else "CHECK",
                detail=(
                    f"Active · {telemetry.policy_gate}"
                    if decision_result
                    else "Run Stage 6 to validate guardrail behavior"
                ),
            ),
        ]

        ready_count = sum(row.status == "READY" for row in checks)
        overall = "DEMO READY" if ready_count == len(checks) else "NEEDS ATTENTION"
        return ReadinessReport(
            checks=checks,
            ready_count=ready_count,
            total_count=len(checks),
            overall_status=overall,
        )
