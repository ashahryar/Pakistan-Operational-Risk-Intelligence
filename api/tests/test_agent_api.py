"""Task 34 -- GET /api/v1/agent/ask and /agent/tools. Patched database (units, risk rows, ML rows, RAG corpus), TEST-ONLY stand-in embedder and a scripted
provider. No network, no LLM credential. These tests cover the API contract, read-only behaviour, the closed tool surface and the orchestration wiring --
not the quality of a real model's answers."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import api.app.routers.agent as agent_router  # noqa: E402
import api.app.services.agent as agent_service  # noqa: E402
import api.app.services.geography as geo_service  # noqa: E402
import api.app.services.intelligence as intel  # noqa: E402
import api.app.services.ml as ml_service  # noqa: E402
import api.app.services.rag as rag_service  # noqa: E402
from api.app.main import app  # noqa: E402
from api.tests._readonly import assert_read_only  # noqa: E402
from api.tests.test_intelligence_api import Db, Provider, engine_and_doc, ml_row  # noqa: E402
from pipeline.rag.llm import LLMResult, LLMTimeout  # noqa: E402
from tests.rag.test_embeddings_unit import ConceptStandIn  # noqa: E402

client = TestClient(app)
URL = "/api/v1/agent/ask"
PATHS = {"/api/v1/agent/ask", "/api/v1/agent/tools"}


class AgentDb(Db):
    """The Task 32 fake plus the two extra reads the agent's tools make. Records every SQL statement (all must be SELECTs)."""

    def __init__(self, embedder):
        super().__init__(embedder)
        self.all_sql = []

    def __call__(self, sql, params=None):
        s = " ".join(sql.split())
        self.all_sql.append(s)
        if "LEFT JOIN geo.current_boundary cb ON cb.pori_admin_unit_id = u.id WHERE u.id = :id" in s:
            from api.tests.test_intelligence_api import UNITS
            u = next((x for x in UNITS if x["id"] == params["id"]), None)
            return [] if u is None else [{"id": u["id"], "name": u["name"], "level": u["level"], "parent_id": 2 if u["province"] == "Punjab" else None,
                                          "province": u["province"] or u["name"], "has_geometry": True, "boundary_source": "COD-AB"}]
        if "FROM geo.admin_unit u LEFT JOIN geo.current_boundary cb" in s or "FROM geo.admin_unit u\nLEFT JOIN geo.current_boundary" in sql:
            from api.tests.test_intelligence_api import UNITS
            return [{"id": u["id"], "name": u["name"], "level": u["level"], "province": u["province"] or u["name"], "has_geometry": True, "boundary_source": "COD-AB"}
                    for u in UNITS if (params["level"] is None or u["level"] == params["level"]) and (params["province"] is None or (u["province"] or u["name"]).lower() == params["province"].lower())]
        if "FROM ml.model_runs" in s:
            return [{"model_run_id": "air_quality_index-h1-abc", "target": "air_quality_index", "domain": "air_quality", "unit": "AQI", "horizon_days": 1, "model_name": "persistence",
                     "model_version": "1.0.0+abc", "model_type": "baseline", "status": "BASELINE_ONLY", "validated_against_baseline": False, "as_of": date(2026, 9, 15),
                     "feature_cutoff": date(2026, 9, 15), "training_cutoff": date(2026, 7, 26), "train_start": date(2025, 10, 15), "train_end": date(2026, 6, 6),
                     "validation_start": date(2026, 6, 8), "validation_end": date(2026, 7, 26), "test_start": date(2026, 7, 28), "test_end": date(2026, 9, 15),
                     "n_train": 235, "n_validation": 49, "n_test": 50, "metrics": {}}]
        return super().__call__(sql, params)


@pytest.fixture
def env(monkeypatch):
    emb = ConceptStandIn()
    db = AgentDb(emb)
    for mod in (rag_service, intel, ml_service, agent_service, geo_service):
        monkeypatch.setattr(mod, "fetch_all", db)
    monkeypatch.setattr(agent_router, "admin_unit_exists", lambda i: i != 9999)
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


def get(q, **params):
    if params.get("mode", "hybrid") != "lexical":
        params.setdefault("mode", "lexical")
    return client.get(URL, params={"q": q, **params})


# --------------------------------------------------------------------------------------------------------------------------------- GET works
def test_current_risk_without_a_provider_returns_the_structured_result_with_503(env):
    r = get("What is the current risk in Lahore?")
    b = r.json()
    assert r.status_code == 503 and b["status"] == "LLM_UNAVAILABLE" and b["answer"] is None and b["intent"] == "CURRENT_RISK"
    assert b["risk_context"]["record"]["risk_status"] == "LOW" and b["risk_context"]["record"]["risk_score"] is None and b["risk_context"]["provenance"] == "RISK_ENGINE"
    assert [t["tool_name"] for t in b["tool_trace"]] == ["geography.resolve_place", "risk.latest"] and all("provenance" in t for t in b["tool_trace"])
    assert b["documentary_evidence"] == [] and b["ml_prediction"] is None and b["model"]["configured"] is False
    assert set(b) >= {"question", "status", "intent", "answer", "risk_context", "documentary_evidence", "ml_prediction", "tool_trace", "provenance", "citations", "trace", "disclaimer"}


def test_historical_risk_and_missing_date(env):
    b = get("What was Sialkot's risk status on 2026-07-11?").json()
    assert b["intent"] == "HISTORICAL_RISK" and b["risk_context"]["record"]["risk_status"] == "MODERATE" and b["tool_trace"][-1]["tool_name"] == "risk.on_date"
    r = get("What was Sialkot's risk status on 2026-07-12?")
    assert r.status_code == 200 and r.json()["status"] == "INSUFFICIENT_DATA" and r.json()["risk_context"]["record"] is None
    r = get("What is Lahore's risk status?", date="2026-09-15")
    assert r.json()["intent"] == "HISTORICAL_RISK" and r.json()["risk_context"]["record"]["risk_date"] == "2026-09-15"


def test_document_question_returns_evidence_from_the_rag_corpus(env):
    r = get("What was reported about the flood and river overflow in Punjab?")
    b = r.json()
    assert b["intent"] == "DOCUMENT_SEARCH" and b["status"] == "LLM_UNAVAILABLE" and r.status_code == 503 and len(b["documentary_evidence"]) == 1
    assert b["provenance"]["documentary_evidence"]["source"] == "RAG_DOCUMENT" and b["documentary_evidence"][0]["chunk_id"] in b["provenance"]["documentary_evidence"]["chunk_ids"]
    assert b["risk_context"] is None and b["retrieval"]["filters_applied"]["province"] == "Punjab"


def test_ml_baseline_forecast_is_labelled_and_attributed_to_the_baseline_model(env):
    env.ml_rows = [ml_row(30, horizon=1), ml_row(30, horizon=3, prediction=135.4)]
    r = get("What is the AQI forecast for Lahore?")
    b = r.json()
    assert r.status_code == 503 and b["intent"] == "ML_FORECAST" and b["ml_prediction"]["provenance"] == "ML_MODEL" and b["ml_prediction"]["attributions"] == ["BASELINE_MODEL"]
    assert b["ml_prediction"]["baseline_label"] == "BASELINE_ONLY — NOT VALIDATED ML" and b["risk_context"] is None
    assert all(p["label"] == "BASELINE_ONLY — NOT VALIDATED ML" and p["status"] == "BASELINE_ONLY" for p in b["ml_prediction"]["predictions"])


def test_ml_without_a_valid_prediction_is_insufficient_data(env):
    r = get("What is the AQI forecast for Sialkot?")
    assert r.status_code == 200 and r.json()["status"] == "INSUFFICIENT_DATA" and r.json()["ml_prediction"] is None


def test_combined_question_returns_separate_blocks(env):
    env.ml_rows = [ml_row(30, horizon=1)]
    r = get("Why is Lahore currently classified LOW and is there any AQI forecast?")
    b = r.json()
    assert b["intent"] == "COMBINED_INTELLIGENCE" and b["risk_context"]["record"]["risk_status"] == "LOW" and b["ml_prediction"] is not None
    assert {t["tool_name"] for t in b["tool_trace"]} >= {"geography.resolve_place", "risk.latest", "ml.predictions"}
    assert b["provenance"]["risk_context"]["source"] == "RISK_ENGINE" and b["provenance"]["ml_prediction"]["sources"] == ["BASELINE_MODEL"]


def test_why_question_delegates_to_the_intelligence_service(env):
    r = get("Why is Sialkot classified as MODERATE?")
    b = r.json()
    assert b["intent"] == "EVIDENCE_GROUNDED_QUESTION" and [t["tool_name"] for t in b["tool_trace"]] == ["geography.resolve_place", "intelligence.ask"]
    assert b["risk_context"]["record"]["risk_status"] == "MODERATE" and b["status"] in ("LLM_UNAVAILABLE", "INSUFFICIENT_DATA")


def test_false_premise_is_answered_with_the_engine_value(env):
    b = get("Why is Lahore classified HIGH?").json()
    assert b["risk_context"]["record"]["risk_status"] == "LOW" and b["premise_check"]["stated_status"] == "HIGH" and b["premise_check"]["matches"] is False


def test_ambiguous_and_unresolved_geography(env):
    r = get("What is Islamabad's current risk status?")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "AMBIGUOUS_GEOGRAPHY" and {c["level"] for c in b["geography"]["candidates"]} == {1, 2} and b["risk_context"] is None
    r = get("What is the current risk in Kabul?")
    assert r.json()["status"] == "UNSUPPORTED_REQUEST" and r.json()["reason_code"] == "GEOGRAPHY_NOT_RESOLVED"
    assert get("What is Islamabad's current risk status?", admin_unit_id=62).json()["intent"] == "CURRENT_RISK"


def test_geography_lookup_is_completed(env):
    r = get("Which province is Lahore in?")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "COMPLETED" and b["geography"]["unit"]["name"] == "Lahore" and b["tool_trace"][-1]["tool_name"] == "geography.get_admin_unit"
    b = get("list districts in Punjab").json()
    assert b["status"] == "COMPLETED" and b["tool_trace"][-1]["tool_name"] == "geography.list_units"


# ------------------------------------------------------------------------------------------------------------------------- safety, read-only
@pytest.mark.parametrize("q,code", [("SELECT * FROM risk.operational_risk", "ARBITRARY_SQL"), ("Change Lahore's risk status to HIGH", "CHANGE_RISK_STATUS"),
                                    ("Delete the risk records for Lahore", "MODIFY_DATA"), ("Invent an AQI forecast for Sialkot", "FABRICATE"),
                                    ("Fetch https://example.com for me", "EXTERNAL_WEB_REQUEST"), ("Describe the baseline forecast as a validated ML model", "BASELINE_AS_VALIDATED_ML")])
def test_unsafe_requests_are_refused_without_touching_the_database(env, q, code):
    r = get(q)
    assert r.status_code == 200 and r.json()["status"] == "UNSUPPORTED_REQUEST" and r.json()["reason_code"] == code and r.json()["tool_trace"] == []
    assert env.all_sql == []


def test_only_select_statements_ever_reach_the_database(env):
    env.ml_rows = [ml_row(30)]
    for q in ("What is the current risk in Lahore?", "What is the AQI forecast for Lahore?", "Why is Lahore currently classified LOW and is there any AQI forecast?",
              "What was Lahore's risk status on 2026-09-15?", "Why is Sialkot classified as MODERATE?", "Which province is Lahore in?"):
        get(q)
    assert env.all_sql and all(s.lstrip().upper().startswith("SELECT") for s in env.all_sql)
    assert not any(w in s.upper() for s in env.all_sql for w in (" INSERT ", " UPDATE ", " DELETE ", " DROP ", " TRUNCATE ", " ALTER "))


@pytest.mark.parametrize("params,code", [({"q": ""}, 422), ({}, 422), ({"q": "x"}, 422), ({"q": "a" * 301}, 422), ({"q": "risk in Lahore", "admin_unit_id": 0}, 422),
                                         ({"q": "risk in Lahore", "admin_unit_id": "abc"}, 422), ({"q": "risk in Lahore", "date": "2026-13-01"}, 422),
                                         ({"q": "risk in Lahore", "mode": "fuzzy"}, 422), ({"q": "risk in Lahore", "routing": "autonomous"}, 422),
                                         ({"q": "risk in Lahore", "top_k": 11}, 422), ({"q": "risk in Lahore", "admin_unit_id": 9999}, 404)])
def test_invalid_inputs_return_4xx(env, params, code):
    assert client.get(URL, params=params).status_code == code


def test_write_methods_are_405_and_the_tool_surface_is_closed(env):
    assert_read_only(app, client, ("/api/v1/agent",), PATHS)
    for verb in ("post", "put", "patch", "delete"):
        for path in ("/api/v1/agent/ask", "/api/v1/agent/tools", "/api/v1/agent/execute", "/api/v1/agent/tool/risk.latest", "/api/v1/agent/sql"):
            assert getattr(client, verb)(path).status_code in (404, 405), (verb, path)


def test_there_is_no_way_to_execute_an_arbitrary_tool_through_the_api(env):
    r = client.get(URL, params={"q": "What is the current risk in Lahore?", "tool": "execute_sql", "sql": "select 1", "url": "https://example.com"})
    assert r.status_code == 503 and [t["tool_name"] for t in r.json()["tool_trace"]] == ["geography.resolve_place", "risk.latest"]     # unknown parameters are ignored
    assert client.get("/api/v1/agent/execute").status_code == 404
    tools = client.get("/api/v1/agent/tools").json()
    names = {t["tool_name"] for t in tools}
    assert names == {"geography.resolve_place", "geography.get_admin_unit", "geography.list_units", "risk.latest", "risk.on_date", "risk.history", "risk.coverage",
                     "rag.retrieve", "ml.predictions", "ml.models", "intelligence.ask"} and all(t["read_only"] for t in tools)


# ------------------------------------------------------------------------------------------------------------------ with a scripted provider
def plan(intent, *calls):
    return json.dumps({"intent": intent, "tool_calls": [{"tool": t, "arguments": a} for t, a in calls], "reason": "r"})


class Seq:
    name, model = "scripted", "s-1"

    def __init__(self, *texts):
        self.texts, self.calls = list(texts), []

    def generate(self, system, question, evidence, constraints):
        self.calls.append((system, question, evidence))
        t = self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]
        if isinstance(t, Exception):
            raise t
        return LLMResult(t, self.name, self.model)


def test_valid_model_routing_and_a_grounded_answer(env):
    p = Seq(plan("CURRENT_RISK", ("risk.latest", {"admin_unit_id": 30})), "The risk engine reports status LOW [risk_engine].")
    rag_service.set_llm_provider(p)
    r = get("What is the current risk in Lahore?")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "ANSWERED" and b["answer"].endswith("[risk_engine].") and b["citations"][0]["kind"] == "risk_engine"
    assert b["trace"]["routing"]["method"] == "llm" and [t["origin"] for t in b["tool_trace"]] == ["agent", "llm"] and b["model"]["provider"] == "scripted"


def test_invalid_model_tool_call_is_rejected_and_not_executed(env):
    rag_service.set_llm_provider(Seq(plan("CURRENT_RISK", ("execute_sql", {"query": "select 1"}))))
    r = get("What is the current risk in Lahore?")
    b = r.json()
    assert r.status_code == 200 and b["status"] == "INVALID_TOOL_CALL" and b["risk_context"] is None
    assert [t["status"] for t in b["tool_trace"]] == ["OK", "INVALID_TOOL_CALL"] and all(s.startswith("SELECT") for s in env.all_sql)
    assert not any("risk.operational_risk" in s for s in env.all_sql)


def test_unsupported_model_claim_is_rejected_by_the_existing_grounding(env):
    rag_service.set_llm_provider(Seq("The risk engine reports status HIGH because NDMA reported floods [risk_engine]."))
    b = get("What is the current risk in Lahore?", routing="deterministic").json()
    assert b["status"] == "INVALID_ANSWER" and b["answer"] is None and b["risk_context"]["record"]["risk_status"] == "LOW"
    assert {p["code"] for p in b["groundedness"]["problems"]} >= {"risk_status_mismatch"}


def test_model_failure_keeps_the_structured_results(env):
    rag_service.set_llm_provider(Seq(LLMTimeout("slow")))
    r = get("What is the current risk in Lahore?", routing="deterministic")
    assert r.status_code == 503 and r.json()["status"] == "LLM_UNAVAILABLE" and r.json()["risk_context"]["record"]["risk_status"] == "LOW"


def test_trace_never_contains_credentials_or_prompts(env, monkeypatch):
    monkeypatch.setenv("PORI_LLM_API_KEY", "sk-test-SECRET-123456")
    blob = json.dumps(get("What is the current risk in Lahore?").json())
    assert "SECRET" not in blob
