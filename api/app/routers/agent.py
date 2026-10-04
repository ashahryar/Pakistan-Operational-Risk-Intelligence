from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.app.schemas.agent import AgentResponse, AgentTool
from api.app.services.agent import ask_agent
from api.app.services.geography import admin_unit_exists
from pipeline.agents.tools import catalogue

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.get("/ask", response_model=AgentResponse,
            responses={503: {"model": AgentResponse, "description": "no real LLM provider is configured/available: the structured tool results are still returned and no answer is generated"}})
def ask(q: str = Query(..., min_length=2, max_length=300, description="a question about operational conditions in Pakistan"),
        admin_unit_id: Optional[int] = Query(None, ge=1, description="province or district; overrides places named in the question"),
        date_: Optional[date] = Query(None, alias="date", description="risk date to look up (exact); default is the latest available record"),
        mode: Literal["lexical", "semantic", "hybrid"] = Query("hybrid", description="how documentary evidence is retrieved"),
        routing: Literal["auto", "deterministic"] = Query("auto", description="auto = LLM-assisted routing when a provider is available, otherwise deterministic"),
        top_k: int = Query(5, ge=1, le=10, description="number of evidence chunks")):
    """Read-only operational intelligence agent: classifies the question, calls only allowlisted read-only tools over the existing risk engine, RAG, ML
    predictions and geography, and returns their results with provenance and an audit trace. It never writes, never queries arbitrary SQL, never creates
    a risk status and never invents an answer: without a real LLM provider the status is LLM_UNAVAILABLE (HTTP 503) with the structured results."""
    if admin_unit_id is not None and not admin_unit_exists(admin_unit_id):
        raise HTTPException(status_code=404, detail=f"admin_unit_id {admin_unit_id} not found in geo.admin_unit")
    body, status = ask_agent(q, admin_unit_id, date_, mode, routing, top_k)
    return body if status == 200 else JSONResponse(status_code=status, content=body)


@router.get("/tools", response_model=list[AgentTool])
def tools():
    """The closed allowlist of agent tools with their typed argument contracts. There is no SQL, file, shell or HTTP tool."""
    return catalogue()
