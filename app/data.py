import random
from datetime import datetime, timedelta, timezone
from .models import Hub, Incident, Shipment

SEED = 42

HUBS = [
    Hub(code='MEM', city='Memphis', country='US', lat=35.1495, lon=-90.0490),
    Hub(code='ORD', city='Chicago', country='US', lat=41.9742, lon=-87.9073),
    Hub(code='DFW', city='Dallas', country='US', lat=32.8998, lon=-97.0403),
    Hub(code='LAX', city='Los Angeles', country='US', lat=33.9416, lon=-118.4085),
    Hub(code='JFK', city='New York', country='US', lat=40.6413, lon=-73.7781),
    Hub(code='ATL', city='Atlanta', country='US', lat=33.6407, lon=-84.4277),
    Hub(code='MIA', city='Miami', country='US', lat=25.7959, lon=-80.2870),
    Hub(code='SEA', city='Seattle', country='US', lat=47.4502, lon=-122.3088),
    Hub(code='AMS', city='Amsterdam', country='NL', lat=52.3105, lon=4.7683),
    Hub(code='FRA', city='Frankfurt', country='DE', lat=50.0379, lon=8.5622),
    Hub(code='LHR', city='London', country='GB', lat=51.4700, lon=-0.4543),
    Hub(code='SIN', city='Singapore', country='SG', lat=1.3644, lon=103.9915),
]

MODE_WEIGHTS = ['air'] * 45 + ['road'] * 35 + ['ocean'] * 15 + ['rail'] * 5
PRIORITY_WEIGHTS = ['standard'] * 70 + ['high'] * 23 + ['critical'] * 7
STATUS_WEIGHTS = ['in_transit'] * 70 + ['planned'] * 20 + ['delayed'] * 10


def generate_shipments(count: int = 1200) -> list[Shipment]:
    rng = random.Random(SEED)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    shipments: list[Shipment] = []

    # Ensure enough traffic touches MEM for the seeded demo incident.
    mem = next(h for h in HUBS if h.code == 'MEM')

    for i in range(count):
        if i < 120:
            origin = mem if i % 2 == 0 else rng.choice([h for h in HUBS if h.code != 'MEM'])
            destination = rng.choice([h for h in HUBS if h.code != origin.code])
            if origin.code != 'MEM' and i % 2 == 1:
                destination = mem
        else:
            origin = rng.choice(HUBS)
            destination = rng.choice([h for h in HUBS if h.code != origin.code])

        mode = rng.choice(MODE_WEIGHTS)
        priority = rng.choice(PRIORITY_WEIGHTS)
        status = rng.choice(STATUS_WEIGHTS)

        depart_offset = rng.randint(-18, 18)
        transit_hours = rng.randint(8, 96)
        departure_ts = now + timedelta(hours=depart_offset)
        eta_ts = departure_ts + timedelta(hours=transit_hours)

        mode_cost_factor = {'air': 2.4, 'road': 1.2, 'ocean': 0.8, 'rail': 0.9}[mode]
        priority_factor = {'standard': 1.0, 'high': 1.15, 'critical': 1.35}[priority]
        base_cost = round(rng.uniform(450, 5500) * mode_cost_factor * priority_factor, 2)

        shipments.append(Shipment(
            shipment_id=f'SHP-{i+1:05d}',
            origin=origin,
            destination=destination,
            mode=mode,
            priority=priority,
            status=status,
            departure_ts=departure_ts,
            eta_ts=eta_ts,
            sla_hours=transit_hours + rng.randint(4, 24),
            base_cost_usd=base_cost,
        ))

    return shipments


def seeded_incident() -> Incident:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return Incident(
        incident_id='INC-MEM-STORM-001',
        title='Severe weather affecting Memphis operations',
        incident_type='severe_weather',
        lat=35.1495,
        lon=-90.0490,
        severity=0.88,
        radius_km=250,
        affected_modes=['air', 'road'],
        detected_at=now,
        expected_duration_hours=14,
        confidence=0.92,
        source='synthetic-demo',
    )
