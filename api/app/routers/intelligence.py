from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.app.schemas.intelligence import IntelligenceResponse
from api.app.services.intelligence import ask_intelligence

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])

INTELLIGENCE_DEFAULT_MODE = "hybrid"      # same retrieval default as /rag/ask


@router.get("/ask", response_model=IntelligenceResponse,
            responses={503: {"model": IntelligenceResponse, "description": "LLM provider not configured/unavailable (risk context and evidence are still returned)"}})
def ask(q: str = Query(..., min_length=2, max_length=300, description="a question about operational risk conditions"),
        admin_unit_id: Optional[int] = Query(None, ge=1, description="province or district; overrides places named in the question"),
        province: Optional[str] = Query(None, description="province name; overrides places named in the question"),
        date_: Optional[date] = Query(None, alias="date", description="risk date to look up (exact); default is the latest available row"),
        date_from: Optional[date] = Query(None, description="documents (and, without `date`, the risk lookup window) from this date"),
        date_to: Optional[date] = None,
        source: Optional[str] = Query(None, description="restrict documentary evidence to one source (ndma, pdma, pmd, ...)"),
        mode: Literal["lexical", "semantic", "hybrid"] = Query(INTELLIGENCE_DEFAULT_MODE, description="how documentary evidence is retrieved"),
        top_k: int = Query(5, ge=1, le=10, description="number of evidence chunks"),
        min_score: Optional[float] = Query(None, ge=0, le=1, description="semantic / hybrid modes: minimum cosine similarity")):
    """Computed risk-engine context (RISK_ENGINE) and retrieved documentary evidence side by side, plus an optional grounded explanation.
    Read-only. Never calculates a risk score; a document is never presented as a risk-engine input. Without an LLM provider it answers 503
    LLM_UNAVAILABLE but still returns the risk context and the evidence."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if min_score is not None and mode == "lexical":
        raise HTTPException(status_code=422, detail="min_score applies to mode=semantic or mode=hybrid only")
    body, status = ask_intelligence(q, admin_unit_id, province, date_, date_from, date_to, source, mode, top_k, min_score)
    return body if status == 200 else JSONResponse(status_code=status, content=body)
