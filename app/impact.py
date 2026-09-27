from math import asin, cos, radians, sin, sqrt
from .models import Incident, IncidentAnalysis, Shipment, ShipmentImpact


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def analyze_incident(incident: Incident, shipments: list[Shipment]) -> IncidentAnalysis:
    impacts: list[ShipmentImpact] = []
    critical_exposed = 0

    for shipment in shipments:
        origin_d = haversine_km(incident.lat, incident.lon, shipment.origin.lat, shipment.origin.lon)
        dest_d = haversine_km(incident.lat, incident.lon, shipment.destination.lat, shipment.destination.lon)
        nearest = min(origin_d, dest_d)
        mode_match = shipment.mode in incident.affected_modes
        within_radius = nearest <= incident.radius_km
        exposed = mode_match and within_radius and shipment.status != 'delivered'

        priority_weight = {'standard': 0.75, 'high': 0.9, 'critical': 1.0}[shipment.priority]
        proximity_weight = max(0.0, 1.0 - (nearest / incident.radius_km)) if within_radius else 0.0
        risk = incident.severity * priority_weight * (0.55 + 0.45 * proximity_weight) if exposed else 0.0
        risk = round(min(1.0, risk), 4)

        reason = None
        if exposed:
            endpoint = shipment.origin.code if origin_d <= dest_d else shipment.destination.code
            reason = f'{shipment.mode} shipment touches {endpoint} inside incident radius'
            if shipment.priority == 'critical':
                critical_exposed += 1

        impacts.append(ShipmentImpact(
            shipment_id=shipment.shipment_id,
            exposed=exposed,
            exposure_reason=reason,
            nearest_distance_km=round(nearest, 1),
            risk_score=risk,
        ))

    impacts.sort(key=lambda x: x.risk_score, reverse=True)
    exposed_count = sum(1 for x in impacts if x.exposed)

    return IncidentAnalysis(
        incident=incident,
        total_shipments=len(shipments),
        exposed_shipments=exposed_count,
        critical_exposed=critical_exposed,
        impacts=impacts,
    )
