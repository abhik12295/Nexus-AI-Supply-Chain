from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Mode = Literal['air','road','ocean','rail']
Priority = Literal['standard','high','critical']
ShipmentStatus = Literal['planned','in_transit','delayed','delivered']

class Hub(BaseModel):
    code: str
    city: str
    country: str
    lat: float
    lon: float

class Shipment(BaseModel):
    shipment_id: str
    origin: Hub
    destination: Hub
    mode: Mode
    priority: Priority
    status: ShipmentStatus
    departure_ts: datetime
    eta_ts: datetime
    sla_hours: int
    base_cost_usd: float = Field(gt=0)

class Incident(BaseModel):
    incident_id: str
    title: str
    incident_type: str
    lat: float
    lon: float
    severity: float = Field(ge=0, le=1)
    radius_km: float = Field(gt=0)
    affected_modes: list[Mode]
    detected_at: datetime
    expected_duration_hours: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    source: str

class ShipmentImpact(BaseModel):
    shipment_id: str
    exposed: bool
    exposure_reason: str | None = None
    nearest_distance_km: float | None = None
    risk_score: float = Field(ge=0, le=1)

class IncidentAnalysis(BaseModel):
    incident: Incident
    total_shipments: int
    exposed_shipments: int
    critical_exposed: int
    impacts: list[ShipmentImpact]
