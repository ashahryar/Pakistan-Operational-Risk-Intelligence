"""Task 32 -- REAL data tests for the intelligence layer (marker `real_model`): the real risk tables, the real corpus and embeddings, the real
embedding model. Skipped without the runtime/weights/stored embeddings (CI). No LLM is involved (the API answers 503 LLM_UNAVAILABLE and still
returns the risk context and evidence), so these check risk-context selection and evidence retrieval, not model behaviour."""

import pytest

from pipeline.rag.embeddings import FastEmbedEmbedder
from tests.rag.test_embeddings_real import live

pytestmark = [pytest.mark.real_model]


@pytest.fixture(scope="module")
def evaluation():
    from scripts.rag.evaluate_intelligence import run
    return run(embedder=FastEmbedEmbedder())


def case(report, cid):
    return next(c for c in report["cases"] if c["id"] == cid)


@live
def test_risk_context_selection_matches_an_independent_sql_read(evaluation):
    s = evaluation["summary"]
    assert s["live_model"] is False and s["risk_context_selection_correct"] == "10/10"
    assert case(evaluation, "risk_lahore_false_premise")["risk_status"] == "LOW"              # the question assumed MODERATE; the engine's value is served
    assert case(evaluation, "risk_ambiguous_islamabad")["geography_status"] == "ambiguous" and case(evaluation, "risk_ambiguous_islamabad")["risk_status"] is None
    assert case(evaluation, "risk_missing_date")["risk_status"] is None                        # no other date is substituted


@live
def test_documentary_evidence_and_unsupported_handling(evaluation):
    s = evaluation["summary"]
    assert s["documentary_evidence_has_expected_term"] == "8/8" and s["unsupported_without_risk_context"] == "4/4"
    assert case(evaluation, "unsupported_cake")["status"] == "RETRIEVAL_EMPTY"
    junk = s["unsupported_junk_chunks_returned"]
    assert junk["unsupported_hurricane"] > 0 and junk["unsupported_bitcoin"] > 0               # known limitation: hybrid retrieval passes keyword junk through


@live
def test_without_a_provider_no_case_produces_an_answer(evaluation):
    assert all(c["status"] in ("LLM_UNAVAILABLE", "NO_RISK_CONTEXT", "RETRIEVAL_EMPTY") for c in evaluation["cases"])
    assert evaluation["summary"]["provenance_probes_as_expected"] == f"{evaluation['summary']['provenance_probe_cases']}/{evaluation['summary']['provenance_probe_cases']}"


@live
def test_risk_and_documents_stay_separate_in_the_real_response():
    from fastapi.testclient import TestClient

    import api.app.services.rag as svc
    from api.app.main import app
    svc.set_embedder(FastEmbedEmbedder())
    svc.set_llm_provider(None)
    try:
        r = TestClient(app).get("/api/v1/intelligence/ask", params={"q": "Why is Sialkot currently classified as MODERATE?"})
        b = r.json()
        assert r.status_code == 503 and b["status"] == "LLM_UNAVAILABLE" and b["answer"] is None
        assert b["risk_context"]["provenance"] == "RISK_ENGINE" and b["risk_context"]["record"]["risk_score"] is None
        assert b["documentary_evidence"] and all("risk_status" not in e for e in b["documentary_evidence"])
        assert r.status_code == 503 and "no LLM provider is configured" in b["model"]["error"]
    finally:
        svc.set_embedder(None)


def test_evaluation_config_is_well_formed():
    import yaml

    from scripts.rag.evaluate_intelligence import CONFIG
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    kinds = {c["kind"] for c in cfg["cases"]}
    ids = [c["id"] for c in cfg["cases"]]
    assert kinds == {"risk", "documentary", "mixed", "unsupported"} and len(ids) == len(set(ids)) == 19
