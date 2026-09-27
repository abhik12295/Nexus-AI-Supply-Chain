from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReplayStage(BaseModel):
    step: int = Field(ge=1, le=6)
    key: str
    name: str
    status: str
    system: str
    headline: str
    summary: str
    facts: list[str] = Field(default_factory=list, max_length=8)
    runtime: list[str] = Field(default_factory=list, max_length=6)


class DecisionReplay(BaseModel):
    incident_id: str
    stages: list[ReplayStage]
    completed_stages: int
    final_outcome: str


class DecisionReplayService:
    """Build a deterministic, presentation-ready replay from already-computed NEXUS state."""

    def build(
        self,
        incident: dict[str, Any],
        analysis: dict[str, Any],
        ai_result: dict[str, Any] | None,
        planner_result: dict[str, Any] | None,
        simulation_result: dict[str, Any] | None,
        evidence_result: dict[str, Any] | None,
        critic_result: dict[str, Any] | None,
        decision_result: dict[str, Any] | None,
        approval_record: dict[str, Any] | None = None,
    ) -> DecisionReplay:
        stages: list[ReplayStage] = []

        stages.append(
            ReplayStage(
                step=1,
                key="detect",
                name="DETECT",
                status="COMPLETE",
                system="Synthetic incident feed",
                headline=str(incident.get("title", "Incident detected")),
                summary=(
                    f'{str(incident.get("incident_type", "")).replace("_", " ").title()} signal '
                    f'with {float(incident.get("severity", 0))*100:.0f}% severity and '
                    f'{float(incident.get("confidence", 0))*100:.0f}% source confidence.'
                ),
                facts=[
                    f'Incident ID: {incident.get("incident_id", "n/a")}',
                    f'Radius: {float(incident.get("radius_km", 0)):.0f} km',
                    f'Affected modes: {", ".join(str(x).upper() for x in incident.get("affected_modes", []))}',
                    f'Expected duration: {float(incident.get("expected_duration_hours", 0)):.0f} hours',
                    f'Source: {incident.get("source", "n/a")}',
                ],
            )
        )

        stages.append(
            ReplayStage(
                step=2,
                key="impact",
                name="IMPACT",
                status="COMPLETE",
                system="Python deterministic impact engine",
                headline=f'{int(analysis.get("exposed_shipments", 0)):,} shipments exposed',
                summary=(
                    "Geospatial and mode matching calculated exposure before any LLM reasoning was used."
                ),
                facts=[
                    f'Total network: {int(analysis.get("total_shipments", 0)):,} shipments',
                    f'Exposed: {int(analysis.get("exposed_shipments", 0)):,}',
                    f'Critical exposed: {int(analysis.get("critical_exposed", 0)):,}',
                    "Source of truth: deterministic Python calculations",
                ],
            )
        )

        if ai_result:
            brief = ai_result.get("brief", {})
            stages.append(
                ReplayStage(
                    step=3,
                    key="analyze",
                    name="ANALYZE",
                    status="COMPLETE",
                    system="NVIDIA Nemotron on Nebius Token Factory",
                    headline="Incident brief generated",
                    summary=str(brief.get("executive_summary", "")),
                    facts=[
                        f'Model confidence: {float(brief.get("confidence", 0))*100:.0f}%',
                        f'Priority actions: {len(brief.get("priority_actions", []) or [])}',
                        f'Watch items: {len(brief.get("watch_items", []) or [])}',
                        "No recovery route selected at this stage",
                    ],
                    runtime=[
                        f'Model: {ai_result.get("model", "n/a")}',
                        f'Latency: {ai_result.get("latency_seconds", "n/a")}s',
                        f'Tokens: {ai_result.get("total_tokens", "n/a")}',
                    ],
                )
            )
        else:
            stages.append(self._pending(3, "analyze", "ANALYZE", "NVIDIA Nemotron on Nebius Token Factory"))

        if planner_result and simulation_result:
            leader = str(simulation_result.get("leader_name", "Unknown"))
            metrics = simulation_result.get("metrics", []) or []
            stages.append(
                ReplayStage(
                    step=4,
                    key="plan",
                    name="PLAN",
                    status="COMPLETE",
                    system="Nemotron Planner + deterministic Python simulator",
                    headline=f"Simulation leader: {leader}",
                    summary=(
                        "Nemotron proposed bounded recovery strategies; Python calculated delay, cost, residual risk, "
                        "SLA exposure, and the composite ranking."
                    ),
                    facts=[
                        f'Strategies evaluated: {len(metrics)}',
                        f'Leader ID: {simulation_result.get("leader_strategy_id", "n/a")}',
                        f'Delay weight: {float(simulation_result.get("weights", {}).get("delay", 0))*100:.0f}%',
                        f'Cost weight: {float(simulation_result.get("weights", {}).get("cost", 0))*100:.0f}%',
                        f'Risk weight: {float(simulation_result.get("weights", {}).get("risk", 0))*100:.0f}%',
                        f'SLA weight: {float(simulation_result.get("weights", {}).get("sla", 0))*100:.0f}%',
                    ],
                    runtime=[
                        f'Planner model: {planner_result.get("model", "n/a")}',
                        f'Planner latency: {planner_result.get("latency_seconds", "n/a")}s',
                        f'Planner tokens: {planner_result.get("total_tokens", "n/a")}',
                    ],
                )
            )
        else:
            stages.append(self._pending(4, "plan", "PLAN", "Nemotron Planner + Python simulator"))

        if critic_result and evidence_result:
            review = critic_result.get("review", {})
            verdict = str(review.get("verdict", "UNKNOWN"))
            stages.append(
                ReplayStage(
                    step=5,
                    key="challenge",
                    name="CHALLENGE",
                    status="COMPLETE",
                    system="Tavily public evidence + Nemotron Critic",
                    headline=f"Critic verdict: {verdict}",
                    summary=str(review.get("summary", "")),
                    facts=[
                        f'Critical issue: {review.get("critical_issue") or "None"}',
                        f'Assessments: {len(review.get("assessments", []) or [])}',
                        f'Tavily searches: {int(evidence_result.get("search_count", 0))}',
                        f'Unique public sources: {int(evidence_result.get("source_count", 0))}',
                        f'Critic confidence: {float(review.get("confidence", 0))*100:.0f}%',
                    ],
                    runtime=[
                        f'Evidence latency: {evidence_result.get("latency_seconds", "n/a")}s',
                        f'Critic model: {critic_result.get("model", "n/a")}',
                        f'Critic latency: {critic_result.get("latency_seconds", "n/a")}s',
                        f'Critic tokens: {critic_result.get("total_tokens", "n/a")}',
                    ],
                )
            )
        else:
            stages.append(self._pending(5, "challenge", "CHALLENGE", "Tavily + Nemotron Critic"))

        if decision_result:
            decision = decision_result.get("decision", {})
            gate = decision_result.get("policy_gate", {})
            status = str(decision.get("decision_status", "UNKNOWN"))
            approval = str((approval_record or {}).get("status", "NOT RECORDED"))
            selected = decision.get("selected_strategy_id")
            stages.append(
                ReplayStage(
                    step=6,
                    key="decide",
                    name="DECIDE",
                    status="COMPLETE",
                    system="Nemotron Decision Agent + deterministic policy gate + human gate",
                    headline=status.replace("_", " "),
                    summary=str(decision.get("summary", "")),
                    facts=[
                        f'Selected strategy: {selected or "None — policy hold"}',
                        f'Policy gate: {"HOLD ENFORCED" if gate.get("must_hold") else "CLEARED"}',
                        f'Critic verdict carried forward: {gate.get("critic_verdict", "n/a")}',
                        f'Stage 6 Tavily searches: {int(decision_result.get("tavily_searches_this_stage", 0))}',
                        f'Human gate: {approval}',
                    ],
                    runtime=[
                        f'Model: {decision_result.get("model", "n/a")}',
                        f'Latency: {decision_result.get("latency_seconds", "n/a")}s',
                        f'Tokens: {decision_result.get("total_tokens", "n/a")}',
                    ],
                )
            )
            final_outcome = status.replace("_", " ")
        else:
            stages.append(self._pending(6, "decide", "DECIDE", "Decision Agent + policy gate"))
            final_outcome = "DECISION PENDING"

        completed = sum(stage.status == "COMPLETE" for stage in stages)
        return DecisionReplay(
            incident_id=str(incident.get("incident_id", "unknown")),
            stages=stages,
            completed_stages=completed,
            final_outcome=final_outcome,
        )

    @staticmethod
    def _pending(step: int, key: str, name: str, system: str) -> ReplayStage:
        return ReplayStage(
            step=step,
            key=key,
            name=name,
            status="PENDING",
            system=system,
            headline="Stage not yet completed",
            summary="Complete the preceding NEXUS workflow stages to populate this replay step.",
            facts=[],
            runtime=[],
        )
