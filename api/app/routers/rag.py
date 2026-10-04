from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from fastapi.responses import JSONResponse

from api.app.schemas.rag import AskResponse, DocumentDetail, DocumentSummary, SearchResponse
from api.app.services.geography import admin_unit_exists
from api.app.services.rag import (
    ask_question,
    get_document,
    list_documents,
    search_evidence,
    search_hybrid_evidence,
    search_semantic_evidence,
)
from pipeline.rag.retrieval import SearchFilters

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

ASK_DEFAULT_MODE = "hybrid"      # /ask is new, so this is a judgement call from the Task 31 evaluation (hybrid is not proven best; see docs); /search stays lexical


def _check(admin_unit_id: Optional[int], date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if admin_unit_id is not None and not admin_unit_exists(admin_unit_id):
        raise HTTPException(status_code=404, detail=f"admin_unit_id {admin_unit_id} not found in geo.admin_unit")


@router.get("/documents", response_model=list[DocumentSummary])
def get_documents(source: Optional[str] = None, source_type: Optional[str] = None, province: Optional[str] = None,
                  admin_unit_id: Optional[int] = Query(None, ge=1), event_type: Optional[str] = None,
                  date_from: Optional[date] = None, date_to: Optional[date] = None,
                  limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """Document metadata (no full text). Documents without a stated date never match a date filter."""
    _check(admin_unit_id, date_from, date_to)
    return list_documents(source, source_type, province, admin_unit_id, event_type, date_from, date_to, limit, offset)


@router.get("/documents/{document_id:path}", response_model=DocumentDetail)
def get_document_detail(document_id: str):
    """One document with its verbatim text and chunk offsets."""
    doc = get_document(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
    return doc


@router.get("/search", response_model=SearchResponse)
def search(q: str = Query(..., min_length=2, max_length=200, description="keywords; lexical match, not semantic"),
           source: Optional[str] = None, source_type: Optional[str] = None, province: Optional[str] = None,
           admin_unit_id: Optional[int] = Query(None, ge=1), event_type: Optional[str] = None,
           date_from: Optional[date] = None, date_to: Optional[date] = None, limit: int = Query(10, ge=1, le=50),
           mode: Literal["lexical", "semantic", "hybrid"] = Query("lexical", description="lexical = BM25 keyword baseline (default); semantic = embedding similarity; hybrid = BM25 + semantic by rank fusion"),
           min_score: Optional[float] = Query(None, ge=0, le=1, description="semantic / hybrid modes: minimum cosine similarity of the semantic component")):
    """Evidence search: returns source chunks with provenance. It does not generate an answer."""
    _check(admin_unit_id, date_from, date_to)
    if min_score is not None and mode == "lexical":
        raise HTTPException(status_code=422, detail="min_score applies to mode=semantic or mode=hybrid only")
    filters = SearchFilters(source=source, source_type=source_type, province=province, admin_unit_id=admin_unit_id,
                            event_type=event_type, date_from=date_from.isoformat() if date_from else None,
                            date_to=date_to.isoformat() if date_to else None)
    if mode == "semantic":
        return search_semantic_evidence(q, filters, limit, min_score)
    if mode == "hybrid":
        return search_hybrid_evidence(q, filters, limit, min_score)
    return search_evidence(q, filters, limit)


@router.get("/ask", response_model=AskResponse,
            responses={503: {"model": AskResponse, "description": "LLM provider not configured/unavailable (evidence is still returned)"}})
def ask(q: str = Query(..., min_length=2, max_length=300, description="a question answerable from the reports"),
        mode: Literal["lexical", "semantic", "hybrid"] = Query(ASK_DEFAULT_MODE, description="how evidence is retrieved"),
        source: Optional[str] = None, province: Optional[str] = None, admin_unit_id: Optional[int] = Query(None, ge=1),
        event_type: Optional[str] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
        top_k: int = Query(5, ge=1, le=10, description="number of evidence chunks given to the model"),
        min_score: Optional[float] = Query(None, ge=0, le=1, description="semantic / hybrid modes: minimum cosine similarity")):
    """Grounded answer: retrieve evidence, have the LLM answer from it only with [chunk:<id>] citations, validate the citations.
    Read-only. Abstains (INSUFFICIENT_EVIDENCE / RETRIEVAL_EMPTY) rather than guessing; evidence is always returned separately."""
    _check(admin_unit_id, date_from, date_to)
    if min_score is not None and mode == "lexical":
        raise HTTPException(status_code=422, detail="min_score applies to mode=semantic or mode=hybrid only")
    filters = SearchFilters(source=source, province=province, admin_unit_id=admin_unit_id, event_type=event_type,
                            date_from=date_from.isoformat() if date_from else None, date_to=date_to.isoformat() if date_to else None)
    body, status = ask_question(q, filters, mode, top_k, min_score)
    return body if status == 200 else JSONResponse(status_code=status, content=body)
