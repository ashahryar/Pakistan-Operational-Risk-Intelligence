"""Task 31 -- OPTIONAL live LLM integration test (marker `live_llm`). Skipped unless PORI_LLM_PROVIDER, PORI_LLM_MODEL and
PORI_LLM_API_KEY are set in the environment; CI never sets them. It makes real provider calls with synthetic evidence."""

import os

import pytest

from pipeline.rag.grounding import ANSWERED, INSUFFICIENT, answer_question
from pipeline.rag.llm import constraints_from_env, provider_from_env

configured = all(os.getenv(k) for k in ("PORI_LLM_PROVIDER", "PORI_LLM_MODEL", "PORI_LLM_API_KEY"))
pytestmark = [pytest.mark.live_llm, pytest.mark.skipif(not configured, reason="no PORI_LLM_* provider configured")]

EVIDENCE = [{"chunk_id": "test:doc#c0000", "document_id": "test:doc", "source": "ndma", "source_type": "sitrep", "title": "Synthetic test report",
             "document_date": "2026-01-01", "geography": {}, "event": {}, "url": None, "file_path": None, "relevance_summary": "synthetic",
             "text": "Synthetic test report: heavy rain fell in the test district on 1 January 2026 and 3 houses were damaged."}]


def test_supported_question_is_answered_with_a_valid_citation():
    o = answer_question("How many houses were damaged in the test district?", EVIDENCE, provider_from_env(), constraints_from_env())
    assert o.status == ANSWERED, (o.status, o.raw_answer, o.validation.problems)
    assert o.validation.citations == ["test:doc#c0000"]


def test_unsupported_question_abstains():
    o = answer_question("What is the capital of France?", EVIDENCE, provider_from_env(), constraints_from_env())
    assert o.status == INSUFFICIENT, (o.status, o.raw_answer)
