"""
api/app/main.py

Task 16A (Phase 1 / ADR-0001) -- minimal FastAPI foundation.

STATUS: real, working, but deliberately small -- 5 endpoints, each
backed by a genuinely existing, reliable Postgres table (see each
router/service module's docstring for exactly which table and why it
was judged reliable enough to serve). No endpoint fabricates data; the
/api/v1/risk endpoint honestly returns an empty list today because its
underlying table has no working loader yet (see
api/app/services/risk.py).

Run locally:
    uvicorn api.app.main:app --reload --port 8000

Not deployed anywhere. Not added to docker-compose.yml in this task
(see Task 16A Part H: "add/maintain containers only where actually
needed" -- no consumer of this API exists yet to justify a running
container).
"""

from __future__ import annotations

from fastapi import FastAPI

from api.app.config import API_DESCRIPTION, API_TITLE, API_VERSION
from api.app.routers import disasters, geography, health, intelligence, rag, risk, weather

app = FastAPI(title=API_TITLE, version=API_VERSION, description=API_DESCRIPTION)

app.include_router(health.router)
app.include_router(geography.router)
app.include_router(weather.router)
app.include_router(disasters.router)
app.include_router(risk.router)
app.include_router(rag.router)
app.include_router(intelligence.router)
