from __future__ import annotations

from services.replay_service import DecisionReplayService
from services.what_if_service import WhatIfService


def main() -> None:
    simulation = {
        "leader_strategy_id": "R2",
        "leader_name": "Reroute All via ATL",
        "weights": {"delay": 0.35, "cost": 0.20, "risk": 0.30, "sla": 0.15},
        "metrics": [
            {
                "strategy_id": "R2",
                "name": "Reroute All via ATL",
                "rank": 1,
                "average_recovery_delay_hours": 6.4,
                "added_cost_usd": 280839,
                "residual_risk": 0.198,
                "sla_exposure_pct": 12.4,
                "composite_score": 0.444,
            },
            {
                "strategy_id": "R1",
                "name": "Hold and Monitor",
                "rank": 2,
                "average_recovery_delay_hours": 13.4,
                "added_cost_usd": 0,
                "residual_risk": 0.674,
                "sla_exposure_pct": 48.3,
                "composite_score": 0.625,
            },
            {
                "strategy_id": "R3",
                "name": "Protect Priority via DFW",
                "rank": 3,
                "average_recovery_delay_hours": 11.6,
                "added_cost_usd": 200889,
                "residual_risk": 0.484,
                "sla_exposure_pct": 37.2,
                "composite_score": 0.648,
            },
        ],
    }

    service = WhatIfService()
    balanced = service.rescore(simulation, service.PRESETS["Balanced · Current"])
    assert balanced.what_if_leader_strategy_id == "R2"
    assert balanced.nemotron_calls == 0
    assert balanced.tavily_searches == 0
    print("Balanced priorities preserve ATL leader: PASS")

    cost_first = service.rescore(simulation, service.PRESETS["Cost First"])
    assert cost_first.what_if_leader_strategy_id == "R1"
    assert cost_first.leader_changed is True
    print("Cost-first priorities can change leader to Hold and Monitor: PASS")

    replay = DecisionReplayService().build(
        incident={
            "incident_id": "INC-MEM-STORM-001",
            "title": "Severe weather affecting Memphis operations",
            "incident_type": "severe_weather",
            "severity": 0.88,
            "confidence": 0.92,
            "radius_km": 250,
            "affected_modes": ["air", "road"],
            "expected_duration_hours": 14,
            "source": "synthetic-demo",
        },
        analysis={"total_shipments": 1200, "exposed_shipments": 234, "critical_exposed": 18},
        ai_result={"brief": {"executive_summary": "Brief", "confidence": .9, "priority_actions": [], "watch_items": []}, "model": "nemotron", "latency_seconds": 1.0, "total_tokens": 100},
        planner_result={"model": "nemotron", "latency_seconds": 1.0, "total_tokens": 100},
        simulation_result=simulation,
        evidence_result={"search_count": 3, "source_count": 12, "latency_seconds": 1.2},
        critic_result={"review": {"verdict": "CAUTION", "summary": "Unverified capacity", "critical_issue": "Capacity", "assessments": [], "confidence": .6}, "model": "nemotron", "latency_seconds": 1.0, "total_tokens": 100},
        decision_result={"decision": {"decision_status": "HOLD_FOR_HUMAN_VALIDATION", "summary": "Hold", "selected_strategy_id": None}, "policy_gate": {"must_hold": True, "critic_verdict": "CAUTION"}, "tavily_searches_this_stage": 0, "model": "nemotron", "latency_seconds": 1.0, "total_tokens": 100},
    )
    assert replay.completed_stages == 6
    assert len(replay.stages) == 6
    assert replay.stages[-1].facts[1] == "Policy gate: HOLD ENFORCED"
    print("Six-stage decision replay builds correctly: PASS")


if __name__ == "__main__":
    main()
