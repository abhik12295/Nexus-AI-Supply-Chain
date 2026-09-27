from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WhatIfMetric(BaseModel):
    strategy_id: str
    name: str
    rank: int = Field(ge=1)
    original_rank: int = Field(ge=1)
    original_score: float
    what_if_score: float
    score_delta: float
    average_recovery_delay_hours: float
    added_cost_usd: float
    residual_risk: float
    sla_exposure_pct: float


class WhatIfResult(BaseModel):
    original_leader_strategy_id: str
    original_leader_name: str
    what_if_leader_strategy_id: str
    what_if_leader_name: str
    leader_changed: bool
    weights: dict[str, float]
    metrics: list[WhatIfMetric]
    nemotron_calls: int = 0
    tavily_searches: int = 0
    policy_gate_changed: bool = False
    note: str


class WhatIfService:
    """Re-rank existing Stage 4 deterministic outcomes under alternate business priorities."""

    PRESETS: dict[str, dict[str, float]] = {
        "Balanced · Current": {"delay": 0.35, "cost": 0.20, "risk": 0.30, "sla": 0.15},
        "Speed First": {"delay": 0.60, "cost": 0.10, "risk": 0.20, "sla": 0.10},
        "Cost First": {"delay": 0.15, "cost": 0.60, "risk": 0.15, "sla": 0.10},
        "Risk First": {"delay": 0.15, "cost": 0.10, "risk": 0.60, "sla": 0.15},
        "SLA Protection": {"delay": 0.15, "cost": 0.10, "risk": 0.15, "sla": 0.60},
    }

    def rescore(
        self,
        simulation: dict[str, Any],
        weights: dict[str, float],
    ) -> WhatIfResult:
        normalized = self.normalize_weights(weights)
        metrics = simulation.get("metrics", []) or []
        if not metrics:
            raise ValueError("What-If Mode requires existing Stage 4 simulation metrics.")

        max_delay = max(float(row.get("average_recovery_delay_hours", 0)) for row in metrics) or 1.0
        max_cost = max(float(row.get("added_cost_usd", 0)) for row in metrics) or 1.0

        rows: list[dict[str, Any]] = []
        for original_rank, row in enumerate(metrics, start=1):
            delay = float(row.get("average_recovery_delay_hours", 0))
            cost = float(row.get("added_cost_usd", 0))
            risk = float(row.get("residual_risk", 0))
            sla_pct = float(row.get("sla_exposure_pct", 0))

            score = (
                normalized["delay"] * (delay / max_delay)
                + normalized["cost"] * (cost / max_cost if max_cost else 0.0)
                + normalized["risk"] * risk
                + normalized["sla"] * (sla_pct / 100.0)
            )
            rows.append(
                {
                    "strategy_id": str(row.get("strategy_id")),
                    "name": str(row.get("name")),
                    "original_rank": int(row.get("rank", original_rank)),
                    "original_score": float(row.get("composite_score", 0)),
                    "what_if_score": round(min(1.0, score), 4),
                    "score_delta": round(min(1.0, score) - float(row.get("composite_score", 0)), 4),
                    "average_recovery_delay_hours": delay,
                    "added_cost_usd": cost,
                    "residual_risk": risk,
                    "sla_exposure_pct": sla_pct,
                }
            )

        ranked = sorted(rows, key=lambda row: row["what_if_score"])
        result_metrics: list[WhatIfMetric] = []
        for rank, row in enumerate(ranked, start=1):
            row["rank"] = rank
            result_metrics.append(WhatIfMetric.model_validate(row))

        original_id = str(simulation.get("leader_strategy_id"))
        original_name = str(simulation.get("leader_name"))
        new_leader = result_metrics[0]
        changed = new_leader.strategy_id != original_id

        return WhatIfResult(
            original_leader_strategy_id=original_id,
            original_leader_name=original_name,
            what_if_leader_strategy_id=new_leader.strategy_id,
            what_if_leader_name=new_leader.name,
            leader_changed=changed,
            weights=normalized,
            metrics=result_metrics,
            note=(
                "What-If Mode only re-scores already-computed Stage 4 outcomes. It does not create a new route, "
                "call Nemotron, search Tavily, change the Stage 5 evidence review, or override the Stage 6 policy gate."
            ),
        )

    @staticmethod
    def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
        clean = {
            "delay": max(0.0, float(weights.get("delay", 0))),
            "cost": max(0.0, float(weights.get("cost", 0))),
            "risk": max(0.0, float(weights.get("risk", 0))),
            "sla": max(0.0, float(weights.get("sla", 0))),
        }
        total = sum(clean.values())
        if total <= 0:
            raise ValueError("At least one What-If weight must be greater than zero.")
        return {key: round(value / total, 6) for key, value in clean.items()}
