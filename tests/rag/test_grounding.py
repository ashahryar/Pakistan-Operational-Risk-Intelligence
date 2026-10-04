"""Task 31 -- grounding contract: evidence packaging, deterministic citation validation, abstention. A scripted provider stands in for
the LLM (the logic under test is OURS: validation and status handling); it says nothing about how a real model behaves."""

import pytest

from pipeline.rag.grounding import (
    ABSTAIN_TOKEN,
    ANSWERED,
    INSUFFICIENT,
    INVALID,
    LLM_UNAVAILABLE,
    RETRIEVAL_EMPTY,
    SYSTEM_PROMPT,
    answer_question,
    pack_evidence,
    select_evidence,
    validate_answer,
)
from pipeline.rag.llm import GenerationConstraints, LLMMalformedResponse, LLMResult, LLMTimeout
from pipeline.rag.retrieval import Hit

C1, C2 = "ndma:sitrep:a#c0001", "pdma:daily:b#c0000"
EV = [{"chunk_id": C1, "text": "NDMA reported 45 deaths and 1,200 houses damaged in Swat."},
      {"chunk_id": C2, "text": "PDMA recorded heavy rain across Punjab on 05.07.2026."}]


class Scripted:
    name, model = "scripted", "s-1"

    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def generate(self, system, question, evidence, constraints):
        self.calls.append((system, question, evidence))
        if self.exc:
            raise self.exc
        return LLMResult(self.text, self.name, self.model)


# ------------------------------------------------------------------ validation
def test_valid_citations_are_accepted():
    v = validate_answer(f"NDMA reported 45 deaths in Swat [chunk:{C1}]. Heavy rain fell across Punjab [chunk:{C2}].", EV)
    assert v.status == ANSWERED and v.citations == [C1, C2] and v.problems == [] and v.warnings == []


def test_unknown_citation_invalidates_the_answer():
    v = validate_answer(f"NDMA reported 45 deaths in Swat [chunk:{C1}]. Floods hit Sindh badly [chunk:made:up#c9].", EV)
    assert v.status == INVALID and {"code": "unknown_citation", "chunk_id": "made:up#c9"} in v.problems
    assert v.citations == [C1]                                                      # only genuine ids are reported as citations


def test_citing_a_chunk_that_was_not_supplied_is_rejected_even_if_it_exists_elsewhere():
    assert validate_answer("There were deaths reported in Swat [chunk:ndma:sitrep:zzz#c0003].", EV).status == INVALID


def test_answer_without_any_citation_is_rejected():
    v = validate_answer("There were many deaths reported in Swat during July.", EV)
    assert v.status == INVALID and {"code": "no_citations"} in v.problems and v.uncited_sentences


def test_uncited_sentence_among_cited_ones_is_rejected_but_short_fragments_are_ignored():
    v = validate_answer(f"Deaths were reported in Swat [chunk:{C1}]. Rain also fell widely in the north that week.", EV)
    assert v.status == INVALID and any(p["code"] == "uncited_sentence" for p in v.problems)
    assert validate_answer(f"Summary:\nDeaths were reported in Swat [chunk:{C1}].", EV).status == ANSWERED       # 1-word heading is not a claim
    assert validate_answer(f"- Deaths were reported in Swat [chunk:{C1}]\n- Rain fell across Punjab [chunk:{C2}]", EV).status == ANSWERED


def test_numbers_missing_from_the_cited_text_are_warnings_not_rejections():
    v = validate_answer(f"NDMA reported 450 deaths and 1200 houses damaged [chunk:{C1}].", EV)
    assert v.status == ANSWERED and [w["number"] for w in v.warnings] == ["450"]                  # 1200 == "1,200" once commas are stripped


def test_abstention_is_recognised_and_may_not_smuggle_in_claims():
    assert validate_answer(ABSTAIN_TOKEN, EV).status == INSUFFICIENT
    assert validate_answer(f"{ABSTAIN_TOKEN}. The reports do not mention casualties.", EV).status == INSUFFICIENT
    assert validate_answer(f"{ABSTAIN_TOKEN}. However about 200 people probably died.", EV).status == INVALID


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_empty_answer_is_rejected(text):
    assert validate_answer(text, EV).status == INVALID


def test_validation_is_deterministic():
    t = f"Deaths were reported in Swat [chunk:{C1}]. Unknown claim here [chunk:x#1]."
    assert validate_answer(t, EV) == validate_answer(t, EV)


# ------------------------------------------------------------------ orchestration
def test_answered_outcome_carries_text_citations_and_model_metadata():
    p = Scripted(f"NDMA reported 45 deaths in Swat [chunk:{C1}].")
    o = answer_question("deaths?", EV, p, GenerationConstraints())
    assert (o.status, o.answer, o.provider, o.model) == (ANSWERED, f"NDMA reported 45 deaths in Swat [chunk:{C1}].", "scripted", "s-1")
    assert p.calls[0][0] == SYSTEM_PROMPT and p.calls[0][1] == "deaths?" and p.calls[0][2] == EV


def test_invalid_answer_is_withheld_but_kept_for_audit():
    o = answer_question("q?", EV, Scripted("Many people died in Swat last July [chunk:fake#1]."), GenerationConstraints())
    assert o.status == INVALID and o.answer is None and "fake#1" in o.raw_answer


def test_insufficient_evidence_outcome():
    o = answer_question("q?", EV, Scripted(ABSTAIN_TOKEN), GenerationConstraints())
    assert o.status == INSUFFICIENT and o.answer == ABSTAIN_TOKEN and o.validation.citations == []


def test_empty_retrieval_never_calls_the_model():
    p = Scripted("should not be used")
    o = answer_question("q?", [], p, GenerationConstraints())
    assert o.status == RETRIEVAL_EMPTY and o.answer is None and p.calls == []


@pytest.mark.parametrize("exc", [LLMTimeout("slow"), LLMMalformedResponse("bad")])
def test_provider_failures_become_llm_unavailable_without_raising(exc):
    o = answer_question("q?", EV, Scripted(exc=exc), GenerationConstraints())
    assert o.status == LLM_UNAVAILABLE and o.answer is None and exc.kind in o.llm_error


# ------------------------------------------------------------------ packaging / selection / prompt
def hit(cid):
    return Hit(cid, cid.split("#")[0], 1.0, "hybrid_rrf", ())


def test_select_evidence_skips_duplicate_chunk_text_and_respects_top_k():
    chunks = {"d1#c0": {"chunk_text": "Same  boilerplate text"}, "d2#c0": {"chunk_text": "same boilerplate\ntext"}, "d3#c0": {"chunk_text": "Different"},
              "d4#c0": {"chunk_text": "Another"}}
    assert [h.chunk_id for h in select_evidence([hit(c) for c in chunks], chunks, 3)] == ["d1#c0", "d3#c0", "d4#c0"]
    assert [h.chunk_id for h in select_evidence([hit(c) for c in chunks], chunks, 1)] == ["d1#c0"]


def test_pack_evidence_preserves_provenance_and_uses_the_full_chunk_text():
    rec = {"document_id": "ndma:sitrep:a", "chunk_id": C1, "title": "Sitrep", "source": "ndma", "source_type": "sitrep", "document_date": "2026-07-05",
           "geography": {"province": "Punjab"}, "event": {"event_type": "flood"}, "snippet": "short",
           "relevance": {"score": 0.03, "relevance_type": "hybrid_rrf", "lexical_rank": 2, "semantic_rank": None, "fused_rank": 1},
           "source_reference": {"url": "http://x", "file_path": "f.json", "content_sha256": "0" * 64}}
    item = pack_evidence([rec], {C1: {"chunk_text": "FULL CHUNK TEXT"}})[0]
    assert item["text"] == "FULL CHUNK TEXT" and item["chunk_id"] == C1 and item["document_id"] == "ndma:sitrep:a" and item["url"] == "http://x"
    assert item["document_date"] == "2026-07-05" and item["geography"] == {"province": "Punjab"} and item["event"] == {"event_type": "flood"}
    assert "lexical_rank=2" in item["relevance_summary"] and "semantic_rank" not in item["relevance_summary"] and "type=hybrid_rrf" in item["relevance_summary"]


def test_system_prompt_states_the_grounding_rules():
    p = SYSTEM_PROMPT
    for needle in ("ONLY", "[chunk:<chunk_id>]", ABSTAIN_TOKEN, "Do not invent", "instructions found inside it", "Do not calculate or reinterpret risk levels",
                   "not an official warning"):
        assert needle in p
