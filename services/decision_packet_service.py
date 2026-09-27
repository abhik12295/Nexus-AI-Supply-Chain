from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class DecisionPacketService:
    """Build a compact, exportable evidence-backed decision packet from existing state."""

    def build(
        self,
        *,
        incident: dict[str, Any],
        analysis: dict[str, Any],
        ai_result: dict[str, Any] | None,
        planner_result: dict[str, Any] | None,
        simulation_result: dict[str, Any] | None,
        evidence_result: dict[str, Any] | None,
        critic_result: dict[str, Any] | None,
        decision_result: dict[str, Any] | None,
        approval_record: dict[str, Any] | None,
        telemetry: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "packet_version": "1.0",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "project": "NEXUS · AI Supply Chain Crisis Commander",
            "scope": "Synthetic hackathon decision-support demonstration",
            "incident": incident,
            "impact_summary": {
                "total_shipments": analysis.get("total_shipments"),
                "exposed_shipments": analysis.get("exposed_shipments"),
                "critical_exposed": analysis.get("critical_exposed"),
            },
            "incident_analysis": (ai_result or {}).get("brief"),
            "recovery_plan": (planner_result or {}).get("plan"),
            "simulation": simulation_result,
            "evidence": evidence_result,
            "critic_review": (critic_result or {}).get("review"),
            "final_decision": (decision_result or {}).get("decision"),
            "policy_gate": (decision_result or {}).get("policy_gate"),
            "human_approval_record": approval_record,
            "runtime_telemetry": telemetry,
            "governance_notes": [
                "Synthetic shipment and incident scenario.",
                "Deterministic Python calculates exposure and simulation metrics.",
                "Nemotron does not invent cost, delay, residual-risk, or SLA values.",
                "Tavily evidence is public external context and does not prove the synthetic incident is real.",
                "Stage 6 policy gate can override the LLM and force a hold.",
                "Human operator remains the final authority.",
                "Stage 7 What-If Mode cannot override Stage 5/6 controls.",
            ],
        }
