"""Task 29 -- RAG foundation: normalization, chunking, geography safety, lexical retrieval, evidence. Fixtures are small and
clearly synthetic (they test the logic); real-corpus checks run against the parsed artifacts when present."""

import copy
import json
from pathlib import Path

import pytest

from pipeline.rag.chunking import chunk_document, chunk_spans
from pipeline.rag.contracts import DOCUMENT_FIELDS, make_chunk_id, make_document_id, sha256_text, validate_chunk, validate_document
from pipeline.rag.evidence import build_evidence
from pipeline.rag.index import build_corpus
from pipeline.rag.normalize import normalize_document, normalize_events, parse_document_date, script_of
from pipeline.rag.retrieval import LexicalRetriever, SearchFilters, matches, tokenize
from pipeline.rag.sources import READERS

REPO = Path(__file__).resolve().parents[2]
LOOKUP = {"Punjab": 2, "Sindh": 3, "Khyber Pakhtunkhwa": 4, "Lahore": 20, "Multan": 21}


def src(**over):
    base = {"source": "ndma", "source_type": "sitrep", "native_id": "abc123", "title": "NDMA Sitrep 1", "text": "Heavy rain and flood warning for Lahore and Multan.",
            "text_fields": None, "date_text": "26 June 2026", "url": None, "file_path": "data/parsed/ndma/sitreps/abc123.json",
            "provinces_raw": ["Punjab", "KP"], "districts_raw": [], "jurisdiction": None, "geography_basis": "mentioned_in_text",
            "event_raw": ["Flood", "Rain"], "ingestion_timestamp": "2026-09-01T00:00:00", "parser_version": None, "published_at": None,
            "metadata": {"report_number": "01"}}
    base.update(over)
    return base


def doc(**over):
    return normalize_document(src(**over), LOOKUP)


# ------------------------------------------------------------------ normalization
def test_document_id_is_stable_and_derived_only_from_the_sources_identifier():
    assert make_document_id("ndma", "sitrep", "6a3e702a90f23") == "ndma:sitrep:6a3e702a90f23"
    assert doc()["document_id"] == doc(title="changed", text="other text")["document_id"]      # content does not change identity
    with pytest.raises(ValueError):
        make_document_id("ndma", "sitrep", "")


def test_canonical_document_has_every_contract_field_and_validates():
    d = doc()
    assert set(DOCUMENT_FIELDS) <= set(d) and validate_document(d) == []
    assert d["content_sha256"] == sha256_text(d["raw_text"]) and d["normalization_version"].startswith("rag-normalize")


def test_source_text_is_never_rewritten():
    messy = "  Heavy  rain\r\n\tflood  ’ \n\n"
    assert doc(text=messy)["raw_text"] == messy


def test_missing_metadata_stays_missing_not_defaulted():
    d = doc(title=None, date_text=None, url=None, provinces_raw=[], event_raw=[], ingestion_timestamp=None)
    assert d["title"] is None and d["document_date"] is None and d["document_date_basis"] == "not_stated"
    assert d["url"] is None and d["published_at"] is None and d["parser_version"] is None and d["ingestion_timestamp"] is None
    assert d["geography_status"] == "not_stated" and d["province"] is None and d["admin_unit_id"] is None
    assert d["event_type"] is None and d["event_types"] == []
    assert validate_document(d) == []


def test_source_provenance_and_metadata_are_preserved():
    d = doc(url="https://example.test/x.pdf", parser_version="tier1-parser-1.0.0", published_at="2026-06-26")
    assert (d["source"], d["file_path"], d["url"], d["parser_version"], d["published_at"]) == (
        "ndma", "data/parsed/ndma/sitreps/abc123.json", "https://example.test/x.pdf", "tier1-parser-1.0.0", "2026-06-26")
    assert d["metadata"] == {"report_number": "01"} and d["ingestion_timestamp"] == "2026-09-01T00:00:00"


def test_dates_only_unambiguous_forms_are_parsed():
    ok = {"26 June 2026": "2026-06-26", "1 AUGUST 2025": "2025-08-01", "1ST DECEMBER 2025": "2025-12-01", "16TH JUNE, 2026": "2026-06-16",
          "2026-09-04": "2026-09-04", " 3rd may 2026 ": "2026-05-03"}
    for text, iso in ok.items():
        assert parse_document_date(text) == (iso, "report_date"), text
    for bad in ("12.07.2026", "3 INDUS 2026", "1 TO 3 JULY 2026", "31 FEBRUARY 2026", "15 جون, 2026 پیر", "tomorrow"):
        assert parse_document_date(bad) == (None, "unparseable"), bad
    assert parse_document_date(None) == (None, "not_stated") and parse_document_date("  ") == (None, "not_stated")


def test_event_types_come_from_the_source_and_are_normalized_without_invention():
    e = normalize_events(["Flood", "Rain", "Flash Flood"])
    assert e["event_types"] == ["flash_flood", "flood", "rainfall"] and e["event_type"] is None and e["event_type_raw"] == ["Flood", "Rain", "Flash Flood"]
    assert normalize_events(["Drought"])["event_type"] == "drought"
    assert normalize_events(["Glacial Lake"])["event_types"] == ["glacial_lake"] and normalize_events([])["event_types"] == []
    assert normalize_events(["Some New Hazard"])["event_types"] == ["some_new_hazard"]            # unknown values pass through, not dropped


def test_script_detection_is_a_measurement_not_a_guess():
    assert script_of("flood warning") == "latin" and script_of("بارش کا امکان ہے") == "arabic" and script_of("123 456") == "other"


# ------------------------------------------------------------------ geography safety
def test_geography_resolves_provinces_through_the_canonical_resolver_and_keeps_original_text():
    d = doc(provinces_raw=["Punjab", "KP", "GB"])
    assert d["provinces"] == ["Gilgit-Baltistan", "Khyber Pakhtunkhwa", "Punjab"] and d["geography_status"] == "resolved_multi"
    assert d["province"] is None and d["admin_unit_id"] is None                  # several provinces: no single unit is claimed
    assert d["geography_text"] == ["Punjab", "KP", "GB"]
    assert d["admin_unit_ids"] == [2, 4]                                          # ids only for units present in the lookup


def test_single_province_sets_the_admin_unit():
    d = doc(provinces_raw=["Sindh"])
    assert (d["province"], d["admin_unit_id"], d["admin_unit_name"], d["geography_status"]) == ("Sindh", 3, "Sindh", "resolved")


def test_unresolved_geography_is_not_fabricated():
    d = doc(provinces_raw=["Atlantis"], districts_raw=["Nowhereville"])
    assert d["geography_status"] == "unresolved" and d["province"] is None and d["admin_unit_id"] is None and d["admin_unit_ids"] == []
    assert d["districts"][0] == {"raw": "Nowhereville", "name": None, "admin_unit_id": None, "status": "unresolved"}
    assert d["geography_text"] == ["Atlantis", "Nowhereville"]                    # original text preserved


def test_near_miss_names_are_not_fuzzy_matched():
    assert doc(provinces_raw=["Punjabb"])["geography_status"] == "unresolved"
    assert doc(districts_raw=["Lahoree"])["districts"][0]["status"] == "unresolved"


def test_partial_resolution_is_reported_as_partial():
    d = doc(provinces_raw=["Punjab"], districts_raw=["Lahore", "Nowhereville"])
    assert d["geography_status"] == "partial" and d["province"] == "Punjab" and [x["status"] for x in d["districts"]] == ["resolved", "unresolved"]
    assert d["admin_unit_ids"] == [2, 20]


def test_caveated_seed_districts_and_gauge_stations_never_become_units():
    d = doc(provinces_raw=[], districts_raw=["Mangla", "Kamra"])
    assert all(x["admin_unit_id"] is None and x["status"] == "unresolved" for x in d["districts"]) and d["geography_status"] == "unresolved"
    assert doc(provinces_raw=[], districts_raw=["Marala", "Tarbela"])["geography_status"] == "unresolved"          # gauge station names are not districts


def test_issuing_authority_jurisdiction_is_recorded_with_its_basis():
    d = doc(source="pdma", source_type="daily_report", jurisdiction="Punjab", provinces_raw=[], districts_raw=["Lahore"],
            geography_basis="issuing_authority_jurisdiction")
    assert d["province"] == "Punjab" and d["admin_unit_id"] == 2 and d["geography_basis"] == "issuing_authority_jurisdiction"
    assert d["admin_unit_ids"] == [2, 20]


def test_without_a_lookup_names_resolve_but_no_ids_are_invented():
    d = normalize_document(src(provinces_raw=["Punjab"]), None)
    assert d["province"] == "Punjab" and d["admin_unit_id"] is None and d["admin_unit_ids"] == []


# ------------------------------------------------------------------ chunking
LONG = " ".join(f"word{i}" for i in range(1200))


def test_chunk_ids_are_deterministic_and_carry_the_document_id():
    d = doc(text=LONG)
    a, b = chunk_document(d), chunk_document(copy.deepcopy(d))
    assert a == b and len(a) > 3
    assert [c["chunk_id"] for c in a] == [make_chunk_id(d["document_id"], i) for i in range(len(a))]
    assert all(c["chunk_id"].startswith(d["document_id"] + "#c") for c in a)


def test_chunks_are_verbatim_slices_with_overlap_and_cover_the_whole_text():
    d = doc(text=LONG)
    cs = chunk_document(d, size=500, overlap=80)
    assert all(validate_chunk(c, d) == [] for c in cs)
    assert all(d["raw_text"][c["char_start"]:c["char_end"]] == c["chunk_text"] for c in cs)
    assert cs[0]["char_start"] == 0 and cs[-1]["char_end"] == len(LONG)
    for prev, nxt in zip(cs, cs[1:]):
        assert nxt["char_start"] < prev["char_end"] and nxt["char_start"] > prev["char_start"]        # overlap, always progressing
    assert all(len(c["chunk_text"]) <= 500 for c in cs)


def test_chunks_cut_on_word_boundaries():
    for c in chunk_document(doc(text=LONG), size=500, overlap=80):
        assert not c["chunk_text"][0:1].isalnum() or c["char_start"] == 0 or LONG[c["char_start"] - 1].isspace()
        assert c["char_end"] == len(LONG) or LONG[c["char_end"]].isspace() or LONG[c["char_end"] - 1].isspace()


def test_short_and_degenerate_texts():
    assert [c["chunk_text"] for c in chunk_document(doc(text="short text"))] == ["short text"]
    assert chunk_spans("") == [] and chunk_spans("   \n  ") == []
    assert chunk_spans("x" * 3000, 1000, 100)[-1][1] == 3000                    # no whitespace: hard cut still terminates
    with pytest.raises(ValueError):
        chunk_spans("abc", 10, 10)


def test_chunks_never_mix_documents_and_stay_stable_on_rerun():
    d1, d2 = doc(native_id="a", text=LONG), doc(native_id="b", text=LONG[::-1])
    c1, c2 = chunk_document(d1), chunk_document(d2)
    assert {c["document_id"] for c in c1} == {d1["document_id"]} and {c["document_id"] for c in c2} == {d2["document_id"]}
    assert not {c["chunk_id"] for c in c1} & {c["chunk_id"] for c in c2}
    assert chunk_document(d1) == c1


def test_validate_chunk_flags_a_rewritten_chunk():
    d = doc(text=LONG)
    c = dict(chunk_document(d)[0])
    c["chunk_text"] = c["chunk_text"].upper()
    assert validate_chunk(c, d)


# ------------------------------------------------------------------ retrieval
def corpus():
    docs = [doc(native_id="n1", text="Flood waters entered Lahore district; evacuation underway.", date_text="1 July 2026", provinces_raw=["Punjab"], event_raw=["Flood"]),
            doc(native_id="n2", text="Heatwave conditions in Sindh with temperatures above 45 degrees.", date_text="5 July 2026", provinces_raw=["Sindh"], event_raw=["Heatwave"]),
            doc(source="pdma", source_type="daily_report", native_id="p1", text="Flood advisory: rain expected in Multan and Lahore.", date_text="10 July 2026",
                provinces_raw=[], jurisdiction="Punjab", event_raw=[]),
            doc(source="pmd", source_type="weekly_outlook", native_id="u1", text="موسم گرم اور خشک رہنے کی توقع", date_text="15 جون, 2026 پیر", provinces_raw=["Punjab"], event_raw=[])]
    chunks = [c for d in docs for c in chunk_document(d)]
    return docs, chunks, LexicalRetriever(docs, chunks)


def ids(hits):
    return [h.document_id.split(":")[-1] for h in hits]


def test_keyword_baseline_ranks_by_term_match_and_is_deterministic():
    docs, chunks, r = corpus()
    hits = r.search("flood lahore", SearchFilters(), 10)
    assert set(ids(hits)) == {"n1", "p1"} and hits[0].score >= hits[1].score and hits[0].method == "lexical_bm25_baseline"
    assert hits == r.search("flood lahore", SearchFilters(), 10) == LexicalRetriever(docs, chunks).search("flood lahore", SearchFilters(), 10)
    assert set(hits[0].matched_terms) <= {"flood", "lahore"}


def test_baseline_is_lexical_not_semantic():
    _, _, r = corpus()
    assert r.search("inundation", SearchFilters(), 5) == []                     # synonym of flood: no semantic matching
    assert r.search("floods", SearchFilters(), 5) == []                         # no stemming either


def test_unicode_text_is_searchable():
    _, _, r = corpus()
    assert ids(r.search("خشک", SearchFilters(), 5)) == ["u1"]


def test_source_filter():
    _, _, r = corpus()
    assert ids(r.search("flood", SearchFilters(source="pdma"), 10)) == ["p1"]
    assert ids(r.search("flood", SearchFilters(source="ndma"), 10)) == ["n1"]


def test_date_filter_excludes_undated_documents_and_respects_bounds():
    _, _, r = corpus()
    assert ids(r.search("flood", SearchFilters(date_from="2026-07-05"), 10)) == ["p1"]
    assert ids(r.search("flood", SearchFilters(date_to="2026-07-05"), 10)) == ["n1"]
    assert r.search("موسم", SearchFilters(date_from="2000-01-01"), 10) == []        # undated (unparseable) never matches a date filter
    assert ids(r.search("موسم", SearchFilters(), 10)) == ["u1"]


def test_geography_filters():
    docs, _, r = corpus()
    assert set(ids(r.search("conditions flood", SearchFilters(province="sindh"), 10))) == {"n2"} or ids(r.search("heatwave", SearchFilters(province="sindh"), 10)) == ["n2"]
    assert set(ids(r.search("flood", SearchFilters(province="Punjab"), 10))) == {"n1", "p1"}
    assert ids(r.search("flood", SearchFilters(admin_unit_id=20), 10)) == []       # no doc resolved Lahore as a district here
    assert set(ids(r.search("flood", SearchFilters(admin_unit_id=2), 10))) == {"n1", "p1"}
    assert matches(docs[0], SearchFilters(province="PUNJAB")) and not matches(docs[0], SearchFilters(province="Sindh"))


def test_event_filter():
    _, _, r = corpus()
    assert ids(r.search("flood", SearchFilters(event_type="flood"), 10)) == ["n1"]
    assert ids(r.search("heatwave sindh", SearchFilters(event_type="heatwave"), 10)) == ["n2"]
    assert r.search("flood", SearchFilters(event_type="earthquake"), 10) == []


def test_empty_and_degenerate_queries_return_nothing():
    _, _, r = corpus()
    assert r.search("zzzzqqqq", SearchFilters(), 5) == [] and r.search("", SearchFilters(), 5) == [] and r.search("flood", SearchFilters(), 0) == []
    assert LexicalRetriever([], []).search("flood", SearchFilters(), 5) == []
    assert tokenize("Flood-water, Lahore!") == ["flood", "water", "lahore"]


def test_scores_do_not_depend_on_filters():
    _, _, r = corpus()
    a = {h.chunk_id: h.score for h in r.search("flood", SearchFilters(), 10)}
    b = {h.chunk_id: h.score for h in r.search("flood", SearchFilters(source="ndma"), 10)}
    assert all(a[k] == v for k, v in b.items())


# ------------------------------------------------------------------ evidence
def test_evidence_is_traceable_and_the_snippet_is_verbatim():
    docs, chunks, r = corpus()
    d = docs[0]
    hit = r.search("evacuation", SearchFilters(), 1)[0]
    chunk = next(c for c in chunks if c["chunk_id"] == hit.chunk_id)
    e = build_evidence(hit, d, chunk)
    assert e["document_id"] == d["document_id"] and e["chunk_id"] == hit.chunk_id and e["source"] == "ndma"
    assert d["raw_text"][e["snippet_document_char_start"]:e["snippet_document_char_end"]] == e["snippet"]      # points back into the source text
    assert "evacuation" in e["snippet"] and e["relevance"]["method"] == "lexical_bm25_baseline"
    assert e["source_reference"] == {"url": None, "file_path": d["file_path"], "content_sha256": d["content_sha256"]}
    assert e["geography"]["provinces"] == ["Punjab"] and e["event"]["event_types"] == ["flood"] and e["document_date"] == "2026-07-01"


def test_evidence_keeps_missing_fields_null():
    _, chunks, r = corpus()
    d = doc(native_id="x", title=None, text="drought watch", date_text=None, provinces_raw=[], event_raw=[])
    ch = chunk_document(d)[0]
    e = build_evidence(r.search("flood", SearchFilters(), 1)[0].__class__(ch["chunk_id"], d["document_id"], 1.0, "m", ("drought",)), d, ch)
    assert e["title"] is None and e["document_date"] is None and e["geography"]["status"] == "not_stated" and e["event"]["event_type"] is None


# ------------------------------------------------------------------ real corpus (skipped when parsed artifacts are absent)
HAVE = (REPO / "data" / "parsed" / "ndma" / "sitreps").exists()


@pytest.mark.skipif(not HAVE, reason="parsed document artifacts not present")
def test_real_corpus_builds_idempotently_with_unique_traceable_ids():
    a, b = build_corpus(REPO, LOOKUP), build_corpus(REPO, LOOKUP)
    assert json.dumps(a["documents"], sort_keys=True) == json.dumps(b["documents"], sort_keys=True) and a["chunks"] == b["chunks"]
    assert len({d["document_id"] for d in a["documents"]}) == len(a["documents"]) > 20
    assert len({c["chunk_id"] for c in a["chunks"]}) == len(a["chunks"])
    docs = {d["document_id"]: d for d in a["documents"]}
    assert all(validate_chunk(c, docs[c["document_id"]]) == [] for c in a["chunks"])
    assert all(validate_document(d) == [] for d in a["documents"])
    assert a["skipped"] == [] or all(s["reason"] for s in a["skipped"])
    assert {n for n, _ in READERS} == set(a["discovered_by_reader"])


@pytest.mark.skipif(not HAVE, reason="parsed document artifacts not present")
def test_real_corpus_never_invents_dates_or_geography():
    a = build_corpus(REPO, {})
    assert a["documents"]
    undated = [d for d in a["documents"] if d["document_date"] is None]
    assert all(d["document_date_basis"] in {"unparseable", "not_stated"} for d in undated)          # whatever is undated stays undated
    no_geo = [d for d in a["documents"] if d["source"] in {"ffc", "pmd_ndmc"}]                       # present only where those artifacts exist
    assert all(d["geography_status"] == "not_stated" and d["province"] is None for d in no_geo)
    assert all(d["admin_unit_id"] is None for d in a["documents"])               # no lookup supplied -> no ids invented
