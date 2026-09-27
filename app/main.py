from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from .data import generate_shipments, seeded_incident
from .impact import analyze_incident
from .models import Incident, IncidentAnalysis, Shipment

app = FastAPI(title='NEXUS API', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

SHIPMENTS = generate_shipments()
INCIDENTS = {seeded_incident().incident_id: seeded_incident()}

@app.get('/health')
def health() -> dict:
    return {'status': 'ok', 'service': 'nexus-api'}

@app.get('/api/shipments', response_model=list[Shipment])
def list_shipments(
    limit: int = Query(default=100, ge=1, le=1200),
    mode: str | None = None,
    priority: str | None = None,
) -> list[Shipment]:
    rows = SHIPMENTS
    if mode:
        rows = [s for s in rows if s.mode == mode]
    if priority:
        rows = [s for s in rows if s.priority == priority]
    return rows[:limit]

@app.get('/api/incidents', response_model=list[Incident])
def list_incidents() -> list[Incident]:
    return list(INCIDENTS.values())

@app.get('/api/incidents/{incident_id}/analysis', response_model=IncidentAnalysis)
def incident_analysis(incident_id: str) -> IncidentAnalysis:
    incident = INCIDENTS.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail='Incident not found')
    return analyze_incident(incident, SHIPMENTS)
