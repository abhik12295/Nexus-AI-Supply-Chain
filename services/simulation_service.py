from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from services.recovery_planner import RecoveryPlan, RecoveryStrategy


DEFAULT_WEIGHTS = {
    "delay": 0.35,
    "cost": 0.20,
    "risk": 0.30,
    "sla": 0.15,
}

MODE_SPEED_KPH = {"air": 720.0, "road": 70.0, "ocean": 32.0, "rail": 55.0}
MODE_HANDLING_HOURS = {"air": 2.5, "road": 1.25, "ocean": 7.0, "rail": 3.5}
MODE_HANDLING_COST = {"air": 320.0, "road": 140.0, "ocean": 680.0, "rail": 240.0}
MODE_DETOUR_COST_FACTOR = {"air": 0.55, "road": 0.72, "ocean": 0.32, "rail": 0.42}


class StrategyMetrics(BaseModel):
    strategy_id: str
    name: str
    strategy_type: str
    routing_hub: str | None = None
    affected_shipments: int
    rerouted_shipments: int
    target_scope_label: str
    target_priority_counts: dict[str, int]
    average_recovery_delay_hours: float
    added_cost_usd: float
    added_cost_per_rerouted_shipment_usd: float
    residual_risk: float = Field(ge=0.0, le=1.0)
    sla_exposure_pct: float = Field(ge=0.0, le=100.0)
    critical_protected_pct: float = Field(ge=0.0, le=100.0)
    composite_score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)
    score_label: str


class SimulationResult(BaseModel):
    leader_strategy_id: str
    leader_name: str
    weights: dict[str, float]
    metrics: list[StrategyMetrics]
    methodology_note: str


class RecoverySimulationService:
    """Deterministic synthetic scenario simulator. No LLM computes any numeric outcome."""

    def simulate(
        self,
        plan: RecoveryPlan,
        incident: dict[str, Any],
        analysis: dict[str, Any],
        shipments: list[dict[str, Any]],
        weights: dict[str, float] | None = None,
    ) -> SimulationResult:
        weights = self._validate_weights(weights or DEFAULT_WEIGHTS)
        by_id = {shipment["shipment_id"]: shipment for shipment in shipments}
        impacts = {impact["shipment_id"]: impact for impact in analysis.get("impacts", []) if impact.get("exposed")}
        exposed_shipments = [by_id[sid] for sid in impacts if sid in by_id]
        hubs = self._hub_index(shipments)

        raw_rows = [
            self._simulate_strategy(strategy, incident, exposed_shipments, impacts, hubs)
            for strategy in plan.strategies
        ]

        max_delay = max(row["average_recovery_delay_hours"] for row in raw_rows) or 1.0
        max_cost = max(row["added_cost_usd"] for row in raw_rows) or 1.0

        for row in raw_rows:
            delay_norm = row["average_recovery_delay_hours"] / max_delay
            cost_norm = row["added_cost_usd"] / max_cost if max_cost > 0 else 0.0
            risk_norm = row["residual_risk"]
            sla_norm = row["sla_exposure_pct"] / 100.0
            row["composite_score"] = round(
                min(
                    1.0,
                    weights["delay"] * delay_norm
                    + weights["cost"] * cost_norm
                    + weights["risk"] * risk_norm
                    + weights["sla"] * sla_norm,
                ),
                4,
            )

        ranked = sorted(raw_rows, key=lambda row: row["composite_score"])
        for rank, row in enumerate(ranked, start=1):
            row["rank"] = rank
            row["score_label"] = "SIMULATION LEADER" if rank == 1 else f"RANK {rank}"

        metrics = [StrategyMetrics.model_validate(row) for row in ranked]
        return SimulationResult(
            leader_strategy_id=metrics[0].strategy_id,
            leader_name=metrics[0].name,
            weights=weights,
            metrics=metrics,
            methodology_note=(
                "Synthetic deterministic scenario model. Delay, cost, residual risk and SLA exposure are calculated "
                "from the generated shipment network, incident severity/duration, route geometry and fixed simulation "
                "coefficients. These are comparative hackathon estimates, not carrier quotes or live capacity commitments."
            ),
        )

    def _simulate_strategy(
        self,
        strategy: RecoveryStrategy,
        incident: dict[str, Any],
        exposed_shipments: list[dict[str, Any]],
        impacts: dict[str, dict[str, Any]],
        hubs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        base_delay = float(incident["expected_duration_hours"]) * (0.65 + 0.35 * float(incident["severity"]))
        alternate_hub = hubs.get(strategy.routing_hub) if strategy.routing_hub else None

        total_delay = 0.0
        total_cost = 0.0
        risk_sum = 0.0
        sla_exposed = 0
        rerouted = 0
        critical_total = 0
        critical_protected = 0
        target_priority_counts = {"critical": 0, "high": 0, "standard": 0}

        for shipment in exposed_shipments:
            impact = impacts[shipment["shipment_id"]]
            priority = shipment["priority"]
            if priority == "critical":
                critical_total += 1

            targeted = self._is_targeted(strategy, priority)
            if targeted:
                target_priority_counts[priority] = target_priority_counts.get(priority, 0) + 1
            if targeted and alternate_hub is not None:
                rerouted += 1
                delay, cost, residual_multiplier = self._reroute_outcome(
                    shipment, alternate_hub, incident, strategy.strategy_type
                )
            else:
                delay = base_delay
                cost = 0.0
                residual_multiplier = 0.95

            residual = min(1.0, float(impact.get("risk_score", 0.0)) * residual_multiplier)
            total_delay += delay
            total_cost += cost
            risk_sum += residual

            slack = self._sla_slack_hours(shipment)
            if delay > slack:
                sla_exposed += 1

            if priority == "critical" and targeted and delay < base_delay and residual_multiplier <= 0.40:
                critical_protected += 1

        count = max(1, len(exposed_shipments))
        critical_pct = 0.0 if critical_total == 0 else (critical_protected / critical_total) * 100.0
        scope_labels = {
            "hold_monitor": "No rerouting · all exposed shipments remain on current paths",
            "reroute_all": "All exposed shipments",
            "protect_priority": "Critical + High exposed shipments",
        }
        return {
            "strategy_id": strategy.strategy_id,
            "name": strategy.name,
            "strategy_type": strategy.strategy_type,
            "routing_hub": strategy.routing_hub,
            "affected_shipments": len(exposed_shipments),
            "rerouted_shipments": rerouted,
            "target_scope_label": scope_labels[strategy.strategy_type],
            "target_priority_counts": target_priority_counts,
            "average_recovery_delay_hours": round(total_delay / count, 2),
            "added_cost_usd": round(total_cost, 2),
            "added_cost_per_rerouted_shipment_usd": round(total_cost / rerouted, 2) if rerouted else 0.0,
            "residual_risk": round(risk_sum / count, 4),
            "sla_exposure_pct": round((sla_exposed / count) * 100.0, 1),
            "critical_protected_pct": round(critical_pct, 1),
            "composite_score": 0.0,
            "rank": 1,
            "score_label": "PENDING",
        }

    @staticmethod
    def _is_targeted(strategy: RecoveryStrategy, priority: str) -> bool:
        if strategy.strategy_type == "hold_monitor":
            return False
        if strategy.strategy_type == "reroute_all":
            return True
        if strategy.strategy_type == "protect_priority":
            return priority in {"critical", "high"}
        return False

    def _reroute_outcome(
        self,
        shipment: dict[str, Any],
        alternate_hub: dict[str, Any],
        incident: dict[str, Any],
        strategy_type: str,
    ) -> tuple[float, float, float]:
        origin = shipment["origin"]
        destination = shipment["destination"]
        direct_km = max(
            50.0,
            self._haversine_km(origin["lat"], origin["lon"], destination["lat"], destination["lon"]),
        )
        reroute_km = self._haversine_km(origin["lat"], origin["lon"], alternate_hub["lat"], alternate_hub["lon"])
        reroute_km += self._haversine_km(
            alternate_hub["lat"], alternate_hub["lon"], destination["lat"], destination["lon"]
        )
        extra_km = max(0.0, reroute_km - direct_km)

        mode = shipment["mode"]
        speed = MODE_SPEED_KPH[mode]
        handling = MODE_HANDLING_HOURS[mode]
        coordination = 1.0
        delay = handling + coordination + (extra_km / speed)

        # Priority-protection scenarios model faster handling but a small premium.
        priority_multiplier = 0.86 if strategy_type == "protect_priority" else 1.0
        delay *= priority_multiplier

        distance_ratio = extra_km / direct_km
        cost = float(shipment["base_cost_usd"]) * distance_ratio * MODE_DETOUR_COST_FACTOR[mode]
        cost += MODE_HANDLING_COST[mode]
        if strategy_type == "protect_priority":
            cost *= 1.10

        alternate_distance = self._haversine_km(
            float(incident["lat"]),
            float(incident["lon"]),
            float(alternate_hub["lat"]),
            float(alternate_hub["lon"]),
        )
        radius = max(1.0, float(incident["radius_km"]))
        separation = min(1.0, alternate_distance / (radius * 3.0))
        residual_multiplier = 0.38 - (0.14 * separation)
        if strategy_type == "protect_priority":
            residual_multiplier *= 0.92
        residual_multiplier = max(0.18, min(0.45, residual_multiplier))

        return max(1.0, delay), max(0.0, cost), residual_multiplier

    @staticmethod
    def _sla_slack_hours(shipment: dict[str, Any]) -> float:
        try:
            departure = datetime.fromisoformat(str(shipment["departure_ts"]).replace("Z", "+00:00"))
            eta = datetime.fromisoformat(str(shipment["eta_ts"]).replace("Z", "+00:00"))
            planned_transit = (eta - departure).total_seconds() / 3600.0
            return max(0.0, float(shipment["sla_hours"]) - planned_transit)
        except Exception:
            return 0.0

    @staticmethod
    def _hub_index(shipments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        hubs: dict[str, dict[str, Any]] = {}
        for shipment in shipments:
            hubs[shipment["origin"]["code"]] = shipment["origin"]
            hubs[shipment["destination"]["code"]] = shipment["destination"]
        return hubs

    @staticmethod
    def _validate_weights(weights: dict[str, float]) -> dict[str, float]:
        required = {"delay", "cost", "risk", "sla"}
        if set(weights) != required:
            raise ValueError(f"weights must contain exactly {sorted(required)}")
        total = sum(float(value) for value in weights.values())
        if total <= 0:
            raise ValueError("simulation weights must sum to a positive value")
        return {key: float(value) / total for key, value in weights.items()}

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0088
        p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
        dlat = math.radians(float(lat2) - float(lat1))
        dlon = math.radians(float(lon2) - float(lon1))
        a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
        return 2 * radius * math.asin(math.sqrt(a))
