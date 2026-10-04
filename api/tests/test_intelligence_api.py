"""Task 32 -- GET /api/v1/intelligence/ask. Patched database (units, risk rows, RAG corpus), TEST-ONLY stand-in embedder, scripted provider.
No network, no LLM credential. These tests cover the API contract, the risk-context lookup, the separation of computed and documentary evidence
and the validation/abstention handling -- not the quality of a real model's explanations."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.services.intelligence as intel  # noqa: E402
import api.app.services.ml as ml_service  # noqa: E402
import api.app.services.rag as rag_service  # noqa: E402
from api.app.main import app  # noqa: E402
from api.tests._readonly import assert_read_only  # noqa: E402
from api.tests.test_rag_semantic_api import FakeDb  # noqa: E402
from pipeline.rag.llm import LLMMalformedResponse, LLMResult, LLMTimeout  # noqa: E402
from tests.rag.test_embeddings_unit import ConceptStandIn  # noqa: E402

client = TestClient(app)
URL = "/api/v1/intelligence/ask"

UNITS = [{"id": 2, "level": 1, "name": "Punjab", "province": None}, {"id": 3, "level": 1, "name": "Sindh", "province": None},
         {"id": 8, "level": 1, "name": "Islamabad Capital Territory", "province": None},
         {"id": 30, "level": 2, "name": "Lahore", "province": "Punjab"}, {"id": 46, "level": 2, "name": "Sialkot", "province": "Punjab"},
         {"id": 50, "level": 2, "name": "Swat", "province": "Khyber Pakhtunkhwa"}, {"id": 62, "level": 2, "name": "Islamabad", "province": "Islamabad Capital Territory"},
         {"id": 9, "level": 1, "name": "Khyber Pakhtunkhwa", "province": None}]


def risk_row(uid, name, status, d, level=2, province="Punjab", rainfall=None):
    return {"admin_unit_id": uid, "admin_unit_name": name, "admin_level": level, "province": province, "risk_date": date.fromisoformat(d), "risk_status": status,
            "risk_basis": "THRESHOLD_BASED", "risk_score": None, "risk_confidence": "MEDIUM", "rainfall_signal": rainfall, "weather_signal": None,
            "gauge_signal": None, "air_quality_signal": None, "hazard_alert_signal": None, "disaster_event_signal": None, "active_signal_count": 1,
            "observed_signal_count": 1, "missing_signal_count": 5, "top_risk_domain": "rainfall" if rainfall else None, "top_risk_contribution": rainfall,
            "data_coverage_pct": 16.67, "source_count": 1, "source_record_count": 1, "calculation_version": "risk-engine-1.0.0", "threshold_status": "PROVISIONAL"}


RISK = [risk_row(46, "Sialkot", "MODERATE", "2026-07-11", rainfall=0.79), risk_row(46, "Sialkot", "LOW", "2026-07-01", rainfall=0.2),
        risk_row(30, "Lahore", "LOW", "2026-09-15"), risk_row(2, "Punjab", "INSUFFICIENT_DATA", "2026-09-16", level=1)]


class Db(FakeDb):
    """The Task 30 fake RAG corpus plus units and risk rows. Records the risk SQL it receives (read-only)."""

    def __init__(self, embedder):
        super().__init__(embedder)
        self.risk_sql = []
        self.ml_rows = []

    def __call__(self, sql, params=None):
        s = " ".join(sql.split())
        if "FROM geo.admin_unit u LEFT JOIN geo.admin_unit p" in s:
            return [dict(u) for u in UNITS]
        if "FROM ml.predictions" in s:
            return [dict(r) for r in self.ml_rows if r["admin_unit_id"] == params["u"] and r["status"] != "INSUFFICIENT_DATA"]
        if "FROM risk.latest_operational_risk" in s:
            self.risk_sql.append(s)
            rows = sorted((r for r in RISK if r["admin_unit_id"] == params["u"]), key=lambda r: r["risk_date"], reverse=True)
            return rows[:1]
        if "FROM risk.operational_risk" in s:
            self.risk_sql.append(s)
            rows = [r for r in RISK if r["admin_unit_id"] == params["u"]]
            if "risk_date = :d" in s:
                rows = [r for r in rows if r["risk_date"] == params["d"]]
            else:
                rows = [r for r in rows if (params["a"] is None or r["risk_date"] >= params["a"]) and (params["b"] is None or r["risk_date"] <= params["b"])]
            return sorted(rows, key=lambda r: r["risk_date"], reverse=True)[:1]
        return super().__call__(sql, params)


class Provider:
    name, model = "scripted", "s-1"

    def __init__(self, fn=None, exc=None):
        self.fn, self.exc, self.calls = fn, exc, []

    def generate(self, system, question, evidence, constraints):
        self.calls.append((system, question, evidence))
        if self.exc:
            raise self.exc
        return LLMResult(self.fn(evidence), self.name, self.model)


def ml_row(uid, status="BASELINE_ONLY", horizon=1, prediction=126.0, validated=False):
    return {"model_run_id": f"air_quality_index-h{horizon}-abc", "entity_type": "admin_unit", "entity_id": str(uid), "admin_unit_id": uid, "horizon_days": horizon,
            "prediction_date": date(2026, 9, 16), "feature_cutoff": date(2026, 9, 15), "target": "air_quality_index", "unit": "AQI", "prediction": prediction,
            "status": status, "reason": None, "model_name": "persistence", "model_version": "1.0.0+abc", "model_type": "baseline" if status == "BASELINE_ONLY" else "ml",
            "training_cutoff": date(2026, 7, 26),
            "provenance": {"provenance": "ML_MODEL", "validated_against_baseline": validated, "note": "forecast"}}


def engine_and_doc(evidence):
    risk = next((e for e in evidence if e.get("kind") == "risk_engine"), None)
    chunks = [e for e in evidence if e.get("kind") != "risk_engine"]
    parts = []
    if risk:
        parts.append(f"The risk engine classifies {risk['record']['admin_unit_name']} as {risk['record']['risk_status']} [risk_engine].")
    if chunks:
        parts.append(f"River overflow was reported in the documents [chunk:{chunks[0]['chunk_id']}].")
    return " ".join(parts)


@pytest.fixture
def env(monkeypatch):
    emb = ConceptStandIn()
    db = Db(emb)
    monkeypatch.setattr(rag_service, "fetch_all", db)
    monkeypatch.setattr(intel, "fetch_all", db)
    monkeypatch.setattr(ml_service, "fetch_all", db)
    rag_service._cache.update(token=None, retriever=None)
    rag_service._sem_cache.update(token=None, retriever=None)
    rag_service._hyb_cache.update(key=None, retriever=None)
    rag_service.set_embedder(emb)
    rag_service.set_llm_provider(None)
    for k in ("PORI_LLM_PROVIDER", "PORI_LLM_MODEL", "PORI_LLM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield db
    rag_service.set_embedder(None)
    rag_service.set_llm_provider(None)
    for c in (rag_service._cache, rag_service._sem_cache):
        c.update(token=None, retriever=None)
    rag_service._hyb_cache.update(key=None, retriever=None)


def ask(**params):
    if params.get("mode", "hybrid") != "lexical":
        params.setdefault("min_score", 0.5)
    return client.get(URL, params=params)


# ------------------------------------------------------------------ success with a (scripted) provider
def test_successful_request_keeps_risk_context_and_documentary_evidence_separate(env):
    p = Provider(engine_and_doc)
    rag_service.set_llm_provider(p)
    r = ask(q="Why is Sialkot classified as MODERATE? River overflow inundation")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "ANSWERED" and b["question_context"]["admin_unit"]["name"] == "Sialkot" and b["question_context"]["target_basis"] == "question_text"
    rec = b["risk_context"]["record"]
    assert b["risk_context"]["status"] == "AVAILABLE" and b["risk_context"]["provenance"] == "RISK_ENGINE" and rec["risk_status"] == "MODERATE"
    assert rec["risk_date"] == "2026-07-11" and rec["risk_score"] is None and rec["signals"]["rainfall"] == 0.79 and rec["calculation_version"] == "risk-engine-1.0.0"
    assert rec["top_risk_domain"] == "rainfall" and rec["data_coverage_pct"] == 16.67 and rec["risk_confidence"] == "MEDIUM" and rec["risk_basis"] == "THRESHOLD_BASED"
    assert b["documentary_evidence"] and all("risk_status" not in e for e in b["documentary_evidence"]) and "chunk_id" not in b["risk_context"]
    kinds = [c["kind"] for c in b["citations"]]
    assert sorted(kinds) == ["documentary", "risk_engine"] and next(c for c in b["citations"] if c["kind"] == "risk_engine")["calculation_version"] == "risk-engine-1.0.0"
    assert b["model"]["configured"] is True and b["groundedness"]["citations_valid"] is True and b["groundedness"]["risk_context_supplied"] is True
    assert b["provenance"]["risk_context"]["source"] == "RISK_ENGINE" and b["provenance"]["documentary_evidence"]["chunk_ids"]
    first = p.calls[0][2][0]
    assert first["kind"] == "risk_engine" and first["record"]["risk_status"] == "MODERATE"            # the engine item reaches the model first and labelled


def test_false_premise_in_the_question_does_not_change_the_engine_status(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="Why is Lahore currently classified as MODERATE? inundation").json()
    assert b["risk_context"]["record"]["risk_status"] == "LOW" and b["question_context"]["latest_requested"] is True and b["status"] == "ANSWERED"


# ------------------------------------------------------------------ risk-context lookup
def test_latest_risk_is_used_by_default_and_a_date_asks_for_that_exact_day(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    assert ask(q="risk in Sialkot flood").json()["risk_context"]["lookup"]["basis"] == "latest"
    b = ask(q="risk in Sialkot flood", date="2026-07-01").json()
    assert b["risk_context"]["record"]["risk_status"] == "LOW" and b["risk_context"]["lookup"] == {"basis": "date", "admin_unit_id": 46, "date": "2026-07-01"}
    assert b["retrieval"]["filters_requested"].get("date_from") is None                              # an explicit risk date does not restrict documents


def test_missing_date_is_no_risk_context_and_never_substitutes_the_latest_row(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    r = ask(q="Why is Sialkot classified as LOW?", date="2026-08-01")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "NO_RISK_CONTEXT" and b["risk_context"]["record"] is None
    assert "no risk record exists for Sialkot on 2026-08-01" in b["risk_context"]["reason"] and b["answer"] is None


def test_date_in_the_question_text_selects_the_risk_row(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="What was the risk in Sialkot on 11 July 2026? inundation").json()
    assert b["risk_context"]["lookup"]["basis"] == "date" and b["risk_context"]["record"]["risk_date"] == "2026-07-11"
    assert b["retrieval"]["filters_requested"]["date_from"] == "2026-07-11"                         # ...and narrows documents (relaxable)


def test_month_window_uses_the_latest_row_inside_the_window(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="risk in Sialkot during July 2026 inundation").json()
    assert b["risk_context"]["lookup"]["basis"] == "window" and b["risk_context"]["record"]["risk_date"] == "2026-07-11"


def test_explicit_admin_unit_overrides_the_text_and_province_parameter_resolves_to_the_province_unit(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="Why is Lahore classified as MODERATE? inundation", admin_unit_id=46).json()
    assert b["question_context"]["target_basis"] == "explicit_admin_unit_id" and b["risk_context"]["record"]["admin_unit_name"] == "Sialkot"
    b = ask(q="operational risk inundation", province="punjab").json()
    assert b["question_context"]["target_basis"] == "explicit_province" and b["risk_context"]["record"]["admin_unit_name"] == "Punjab"
    assert b["risk_context"]["record"]["risk_status"] == "INSUFFICIENT_DATA"


def test_ambiguous_place_is_not_guessed(env):
    r = ask(q="Why is Islamabad classified as HIGH risk?")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "NO_RISK_CONTEXT" and b["question_context"]["geography_status"] == "ambiguous"
    assert "ambiguous" in b["risk_context"]["reason"] and env.risk_sql == []                          # no risk query was run for a guessed unit


def test_unknown_unit_and_unresolved_province_parameter(env):
    assert ask(q="risk in Sialkot", admin_unit_id=999).status_code == 404
    b = ask(q="operational risk inundation", province="Narnia").json()
    assert b["risk_context"]["status"] == "NO_RISK_CONTEXT" and b["retrieval"]["filters_requested"] == {"province": "Narnia", "event_type": "flood"}      # original province text preserved
    assert b["question_context"]["province_parameter_unresolved"] == "Narnia"


# ------------------------------------------------------------------ assembly outcomes
def test_no_risk_context_with_documents_returns_the_documents_without_calling_the_model(env):
    p = Provider(engine_and_doc)
    rag_service.set_llm_provider(p)
    b = ask(q="Why is Lahore classified as LOW risk? inundation", date="2026-01-01").json()        # Lahore has no risk row on that date
    assert b["status"] == "NO_RISK_CONTEXT" and b["documentary_evidence"] and p.calls == []
    assert b["retrieval"]["filters_relaxed"] == ["event_type", "district_to_province"] and b["retrieval"]["filters_applied"] == {"province": "Punjab"}
    b = ask(q="Why is Swat classified as HIGH risk?").json()                                      # a district with no risk row at all
    assert b["status"] == "NO_RISK_CONTEXT" and "no risk record exists for Swat" in b["risk_context"]["reason"] and p.calls == []


def test_documents_without_risk_context_are_explained_when_the_question_is_not_about_a_classification(env):
    p = Provider(engine_and_doc)
    rag_service.set_llm_provider(p)
    b = ask(q="River overflow inundation reported").json()
    assert b["status"] == "ANSWERED" and b["risk_context"]["status"] == "NO_RISK_CONTEXT" and all(e.get("kind") != "risk_engine" for e in p.calls[0][2])
    assert [c["kind"] for c in b["citations"]] == ["documentary"]


def test_risk_without_documents_is_explained_from_the_engine_alone(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="What is the operational risk status in Lahore xyzzy?", source="pdma", mode="lexical").json()
    assert b["documentary_evidence"] == [] and b["risk_context"]["status"] == "AVAILABLE" and b["status"] == "ANSWERED"
    assert [c["kind"] for c in b["citations"]] == ["risk_engine"]


def test_neither_risk_nor_documents_is_retrieval_empty(env):
    r = ask(q="xyzzy plugh", mode="lexical")
    assert r.status_code == 200 and r.json()["status"] == "RETRIEVAL_EMPTY" and r.json()["documentary_evidence"] == [] and r.json()["answer"] is None


def test_filters_are_relaxed_only_for_inferred_narrowing_and_reported(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="heatwave in Punjab river overflow", source="ndma").json()                           # only the pdma document is a heatwave: strict search finds none
    r = b["retrieval"]
    assert r["filters_requested"] == {"province": "Punjab", "event_type": "heatwave", "source": "ndma"}
    assert r["filters_relaxed"] == ["event_type"] and r["filters_applied"] == {"province": "Punjab", "source": "ndma"} and b["documentary_evidence"]
    assert all(e["source"] == "ndma" for e in b["documentary_evidence"])


# ------------------------------------------------------------------ no provider / provider failures
def test_without_a_provider_the_response_still_has_risk_context_and_evidence_and_no_fake_answer(env):
    r = ask(q="Why is Sialkot classified as MODERATE? inundation")
    b = r.json()
    assert r.status_code == 503 and b["status"] == "LLM_UNAVAILABLE" and b["answer"] is None and b["citations"] == []
    assert b["risk_context"]["record"]["risk_status"] == "MODERATE" and b["documentary_evidence"]
    assert b["model"]["configured"] is False and "no LLM provider is configured" in b["model"]["error"]


@pytest.mark.parametrize("exc", [LLMTimeout("slow"), LLMMalformedResponse("bad")])
def test_provider_failure_is_llm_unavailable_with_context_preserved(env, exc):
    rag_service.set_llm_provider(Provider(exc=exc))
    r = ask(q="Why is Sialkot classified as MODERATE? inundation")
    assert r.status_code == 503 and r.json()["status"] == "LLM_UNAVAILABLE" and r.json()["risk_context"]["status"] == "AVAILABLE" and r.json()["documentary_evidence"]


# ------------------------------------------------------------------ grounding through the API
def test_unknown_citation_is_rejected_and_withheld(env):
    rag_service.set_llm_provider(Provider(lambda ev: "Flooding was reported across the district [chunk:made:up#c9]."))
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["status"] == "INVALID_ANSWER" and b["answer"] is None and b["citations"] == []
    assert {"code": "unknown_citation", "chunk_id": "made:up#c9"} in b["groundedness"]["problems"] and b["groundedness"]["rejected_answer_text"]
    assert b["risk_context"]["status"] == "AVAILABLE" and b["documentary_evidence"]


def test_a_fabricated_causal_link_is_rejected(env):
    rag_service.set_llm_provider(Provider(lambda ev: "The risk engine classifies Sialkot as MODERATE because NDMA reported flooding [risk_engine]."))
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["status"] == "INVALID_ANSWER" and any(p["code"] == "engine_sentence_attributes_to_documents" for p in b["groundedness"]["problems"])


def test_a_wrong_engine_status_is_rejected(env):
    rag_service.set_llm_provider(Provider(lambda ev: "The risk engine classifies Lahore as MODERATE [risk_engine]."))
    b = ask(q="Why is Lahore currently classified as MODERATE? inundation").json()
    assert b["status"] == "INVALID_ANSWER" and any(p["code"] == "risk_status_mismatch" for p in b["groundedness"]["problems"])


def test_model_abstention_is_insufficient_evidence(env):
    rag_service.set_llm_provider(Provider(lambda ev: "INSUFFICIENT_EVIDENCE"))
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["status"] == "INSUFFICIENT_EVIDENCE" and b["citations"] == [] and b["risk_context"]["status"] == "AVAILABLE"


# ------------------------------------------------------------------ validation and read-only
@pytest.mark.parametrize("params", [{"mode": "bogus"}, {"mode": ""}, {"top_k": 0}, {"top_k": 11}, {"top_k": "abc"}, {"date": "not-a-date"}, {"date": "2026-13-45"},
                                    {"date_from": "2026-08-01", "date_to": "2026-07-01"}, {"mode": "lexical", "min_score": 0.5}, {"min_score": 1.5},
                                    {"admin_unit_id": 0}, {"q": "x"}])
def test_invalid_parameters_are_422(env, params):
    base = {"q": "risk in Sialkot"}
    base.update(params)
    assert client.get(URL, params=base).status_code == 422


def test_missing_question_is_422(env):
    assert client.get(URL).status_code == 422


def test_the_intelligence_api_is_read_only(env):
    assert_read_only(app, client, ("/api/v1/intelligence",), {"/api/v1/intelligence/ask"})
    for verb in ("post", "put", "patch", "delete"):
        assert getattr(client, verb)(URL + "?q=risk").status_code == 405
    assert all(s.startswith("SELECT") for s in env.risk_sql)                                           # only reads reached the database


def test_existing_endpoints_are_unaffected(env):
    assert client.get("/api/v1/rag/search", params={"q": "inundation"}).json()["mode"] == "lexical"
    assert client.get("/api/v1/rag/ask", params={"q": "inundation", "min_score": 0.5}).status_code in (200, 503)


# ------------------------------------------------------------------ Task 33: the ML forecast is a separate, optional block
def test_ml_prediction_is_null_when_no_valid_forecast_exists(env):
    rag_service.set_llm_provider(Provider(engine_and_doc))
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["ml_prediction"] is None and b["provenance"]["ml_prediction"] == {"source": "ML_MODEL", "available": False, "model_run_ids": []}
    env.ml_rows = [ml_row(46, status="INSUFFICIENT_DATA", prediction=None)]
    assert ask(q="Why is Sialkot classified as MODERATE? inundation").json()["ml_prediction"] is None


def test_ml_prediction_is_present_labelled_ml_model_and_never_merged_into_risk_context(env):
    env.ml_rows = [ml_row(46), ml_row(46, horizon=3, prediction=135.4)]
    rag_service.set_llm_provider(None)
    r = ask(q="Why is Sialkot classified as MODERATE? inundation")
    b = r.json()
    ml = b["ml_prediction"]
    assert r.status_code == 503 and b["status"] == "LLM_UNAVAILABLE"                                    # no provider: the forecast is still returned
    assert ml["provenance"] == "ML_MODEL" and ml["kind"] == "forecast_of_observed_quantity" and ml["validated_against_baseline"] is False
    assert [p["horizon_days"] for p in ml["predictions"]] == [1, 3] and ml["predictions"][0]["prediction"] == 126.0 and "not a current risk classification" in ml["note"]
    assert b["risk_context"]["record"]["risk_status"] == "MODERATE" and "prediction" not in str(b["risk_context"]) and "ML_MODEL" not in str(b["risk_context"])
    assert b["provenance"]["ml_prediction"]["available"] is True and b["provenance"]["ml_prediction"]["model_run_ids"]


def test_the_model_receives_the_forecast_as_a_labelled_item_and_a_valid_ml_sentence_is_cited(env):
    env.ml_rows = [ml_row(46)]
    p = Provider(lambda ev: "The risk engine classifies Sialkot as MODERATE [risk_engine]. The ML layer forecasts an AQI of 126 for 2026-09-16 [ml_prediction].")
    rag_service.set_llm_provider(p)
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["status"] == "ANSWERED" and sorted(c["kind"] for c in b["citations"]) == ["ml_prediction", "risk_engine"]
    kinds = [e.get("kind") or "chunk" for e in p.calls[0][2]]
    assert kinds[:2] == ["risk_engine", "ml_prediction"] and set(kinds[2:]) == {"chunk"}


@pytest.mark.parametrize("sentence,code", [
    ("The ML layer forecasts that Sialkot risk is HIGH tomorrow [ml_prediction].", "ml_prediction_described_as_risk_status"),
    ("The current AQI is predicted to be 126 [ml_prediction].", "ml_prediction_described_as_current_or_risk"),
    ("Sialkot is at 126 AQI for 2026-09-16 according to the model [ml_prediction].", "ml_sentence_not_framed_as_prediction"),
    ("The forecast of 126 AQI is confirmed by the engine [risk_engine] [ml_prediction].", "mixed_provenance_sentence")])
def test_ml_forecast_described_as_current_or_as_a_risk_status_is_rejected(env, sentence, code):
    env.ml_rows = [ml_row(46)]
    rag_service.set_llm_provider(Provider(lambda ev, s=sentence: s))
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["status"] == "INVALID_ANSWER" and any(p["code"] == code for p in b["groundedness"]["problems"])


def test_ml_citation_without_a_forecast_is_rejected(env):
    rag_service.set_llm_provider(Provider(lambda ev: "The model forecasts an AQI of 126 for tomorrow [ml_prediction]."))
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["status"] == "INVALID_ANSWER" and any(p["code"] == "ml_citation_without_prediction" for p in b["groundedness"]["problems"])


def test_ml_forecast_for_an_area_other_than_the_asked_one_is_not_shown(env):
    env.ml_rows = [ml_row(30)]
    b = ask(q="Why is Sialkot classified as MODERATE? inundation").json()
    assert b["ml_prediction"] is None
