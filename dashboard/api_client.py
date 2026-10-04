"""dashboard/api_client.py

Task 27 -- small HTTP client for the PORI FastAPI serving layer. The Streamlit dashboard consumes geography and
operational risk ONLY through this client (never through the risk engine, pipeline or database). It never raises to
the UI: every outcome is an ApiResult with ok / data / error_kind / message, so a page can degrade gracefully.

Base URL: environment variable PORI_API_URL (default http://localhost:8000).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 20.0

_MESSAGES = {
    "not_found": "The requested area was not found (HTTP 404).",
    "invalid_request": "The API rejected the filter values (HTTP 422).",
    "unavailable": "The API reported that its database is unavailable (HTTP 503).",
    "timeout": "The API did not respond in time.",
    "connection": "The API is not reachable. Is it running (uvicorn api.app.main:app)?",
    "server_error": "The API returned an unexpected error.",
    "bad_response": "The API returned a response that could not be read.",
}


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    data: Any = None
    error_kind: Optional[str] = None      # not_found | invalid_request | unavailable | timeout | connection | server_error | bad_response
    message: Optional[str] = None
    status_code: Optional[int] = None

    @property
    def empty(self) -> bool:
        return self.ok and not self.data


def _clean(params: Optional[dict]) -> dict:
    return {k: v for k, v in (params or {}).items() if v is not None}


class RiskApiClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT, session: Optional[requests.Session] = None):
        self.base_url = (base_url or os.getenv("PORI_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()

    def _get(self, path: str, params: Optional[dict] = None, timeout: Optional[float] = None) -> ApiResult:
        try:
            resp = self._session.get(f"{self.base_url}{path}", params=_clean(params), timeout=timeout or self.timeout)
        except requests.Timeout:
            return ApiResult(False, error_kind="timeout", message=_MESSAGES["timeout"])
        except requests.ConnectionError:
            return ApiResult(False, error_kind="connection", message=_MESSAGES["connection"])
        except requests.RequestException:
            return ApiResult(False, error_kind="connection", message=_MESSAGES["connection"])
        code = resp.status_code
        if code == 200:
            try:
                return ApiResult(True, data=resp.json(), status_code=200)
            except ValueError:
                return ApiResult(False, error_kind="bad_response", message=_MESSAGES["bad_response"], status_code=200)
        kind = {404: "not_found", 422: "invalid_request", 503: "unavailable"}.get(code, "server_error")
        detail = None
        try:
            body = resp.json()
            if kind == "unavailable" and isinstance(body, dict) and ("answer_status" in body or "risk_context" in body):      # /rag/ask and /intelligence/ask: the evidence is still useful
                return ApiResult(False, data=body, error_kind=kind, message=_MESSAGES[kind], status_code=code)
            d = body.get("detail") if isinstance(body, dict) else None
            detail = d if isinstance(d, str) else None
        except ValueError:
            pass
        msg = _MESSAGES[kind] + (f" ({detail})" if detail and kind in ("not_found",) else "")
        if kind == "unavailable" and detail and path.startswith(("/api/v1/rag/", "/api/v1/intelligence/")):
            msg = f"This feature is unavailable: {detail}"
        return ApiResult(False, error_kind=kind, message=msg, status_code=code)

    # -- geography
    def admin_units(self, level: Optional[int] = None, province: Optional[str] = None, limit: int = 500) -> ApiResult:
        return self._get("/api/v1/geography/admin-units", {"level": level, "province": province, "limit": limit})

    def boundaries(self, level: Optional[int] = None, province: Optional[str] = None, source: Optional[str] = None,
                   limit: int = 500) -> ApiResult:
        return self._get("/api/v1/geography/boundaries", {"level": level, "province": province, "source": source, "limit": limit})

    # -- risk
    def risk_latest(self, province: Optional[str] = None, admin_unit_id: Optional[int] = None, risk_status: Optional[str] = None,
                    limit: int = 500) -> ApiResult:
        return self._get("/api/v1/risk/latest", {"province": province, "admin_unit_id": admin_unit_id, "risk_status": risk_status, "limit": limit})

    def risk(self, date: Optional[str] = None, province: Optional[str] = None, admin_unit_id: Optional[int] = None,
             risk_status: Optional[str] = None, limit: int = 200, offset: int = 0) -> ApiResult:
        return self._get("/api/v1/risk", {"date": date, "province": province, "admin_unit_id": admin_unit_id,
                                          "risk_status": risk_status, "limit": limit, "offset": offset})

    def risk_map(self, level: Optional[int] = None, province: Optional[str] = None, risk_status: Optional[str] = None,
                 only_with_risk: bool = False, include_geometry: bool = True) -> ApiResult:
        return self._get("/api/v1/risk/map", {"level": level, "province": province, "risk_status": risk_status,
                                              "only_with_risk": str(bool(only_with_risk)).lower(),
                                              "include_geometry": str(bool(include_geometry)).lower()})

    # -- rag (Task 31)
    def ask(self, q: str, mode: str = "hybrid", source: Optional[str] = None, province: Optional[str] = None, top_k: int = 5) -> ApiResult:
        """Grounded answer. A 503 whose body carries an answer_status (no LLM configured) comes back as ok=False with data = that body."""
        return self._get("/api/v1/rag/ask", {"q": q, "mode": mode, "source": source, "province": province, "top_k": top_k}, timeout=90.0)

    # -- intelligence (Task 32)
    def intelligence(self, q: str, mode: str = "hybrid", admin_unit_id: Optional[int] = None, province: Optional[str] = None,
                     date: Optional[str] = None, top_k: int = 5) -> ApiResult:
        """Risk context + documentary evidence (+ optional grounded explanation). A 503 carrying a body (no LLM) comes back as ok=False with data = body."""
        return self._get("/api/v1/intelligence/ask", {"q": q, "mode": mode, "admin_unit_id": admin_unit_id, "province": province, "date": date,
                                                       "top_k": top_k}, timeout=90.0)

    # -- ML predictions (Task 33)
    def ml_predictions(self, admin_unit_id: Optional[int] = None, horizon: Optional[int] = None, date: Optional[str] = None,
                       include_insufficient: bool = True) -> ApiResult:
        return self._get("/api/v1/ml/predictions", {"admin_unit_id": admin_unit_id, "horizon": horizon, "date": date,
                                                    "include_insufficient": str(bool(include_insufficient)).lower()})
