from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The deterministic simulator itself does not call OpenAI. This fallback only lets
# the smoke test run in minimal environments where the Stage 3 client is absent.
try:
    import openai  # noqa: F401
except ModuleNotFoundError:
    import types
    stub = types.ModuleType("openai")
    class OpenAI:  # pragma: no cover - test-only import shim
        pass
    stub.OpenAI = OpenAI
    sys.modules["openai"] = stub

from app.data import generate_shipments, seeded_incident
from app.impact import analyze_incident
from services.recovery_planner import RecoveryPlan
from services.simulation_service import RecoverySimulationService


shipments = [row.model_dump(mode="json") for row in generate_shipments(1200)]
incident_model = seeded_incident()
incident = incident_model.model_dump(mode="json")
analysis = analyze_incident(incident_model, generate_shipments(1200)).model_dump(mode="json")

plan = RecoveryPlan.model_validate(
    {
        "planning_summary": "Static Stage 4 simulator smoke test.",
        "strategies": [
            {
                "strategy_id": "R1",
                "name": "Maintain and Monitor",
                "strategy_type": "hold_monitor",
                "routing_hub": None,
                "description": "Maintain current paths while monitoring Memphis.",
                "rationale": "Provides a no-reroute baseline.",
                "assumptions": [],
            },
            {
                "strategy_id": "R2",
                "name": "Network Diversion via DFW",
                "strategy_type": "reroute_all",
                "routing_hub": "DFW",
                "description": "Reroute all exposed shipments through DFW in the synthetic scenario.",
                "rationale": "Tests a broad diversion scenario.",
                "assumptions": ["DFW capacity is not verified."],
            },
            {
                "strategy_id": "R3",
                "name": "Priority Protection via ORD",
                "strategy_type": "protect_priority",
                "routing_hub": "ORD",
                "description": "Reroute critical/high shipments through ORD while standard shipments remain on current paths.",
                "rationale": "Tests selective protection of priority flows.",
                "assumptions": ["ORD capacity is not verified."],
            },
        ],
        "planning_assumptions": ["Synthetic scenario only."],
    }
)

result = RecoverySimulationService().simulate(plan, incident, analysis, shipments)
print(f"Simulation leader: {result.leader_name}")
for row in result.metrics:
    print(
        row.strategy_id,
        row.name,
        f"delay={row.average_recovery_delay_hours}h",
        f"cost=${row.added_cost_usd:,.0f}",
        f"risk={row.residual_risk:.3f}",
        f"sla={row.sla_exposure_pct:.1f}%",
        f"score={row.composite_score:.3f}",
        f"target={row.target_scope_label}",
        f"counts={row.target_priority_counts}",
    )

priority = next(row for row in result.metrics if row.strategy_type == "protect_priority")
assert priority.rerouted_shipments == (
    priority.target_priority_counts.get("critical", 0)
    + priority.target_priority_counts.get("high", 0)
), "protect_priority reroute count must equal Critical + High targets"
assert priority.target_priority_counts.get("standard", 0) == 0, (
    "protect_priority must never target Standard shipments"
)
print("Priority-scope contract: PASS")
