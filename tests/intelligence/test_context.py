"""Task 32 -- deterministic question-context extraction (place / date / event). Pure functions; the admin-unit rows are built from the
project's own canonical geography with made-up ids (the real ids come from geo.admin_unit at run time)."""

import pytest

from pipeline.intelligence.context import extract_context, find_dates, find_events
from scripts.geo.canonical_data import DISTRICTS, PROVINCES


def make_units():
    units, next_id = [], 1
    for p in PROVINCES:
        units.append({"id": next_id, "level": 1, "name": p["name"], "province": None})
        next_id += 1
    for d in DISTRICTS:
        units.append({"id": next_id, "level": 2, "name": d["name"], "province": d["province"]})
        next_id += 1
    return units


UNITS = make_units()
BY_NAME = {(u["level"], u["name"]): u for u in UNITS}


def ctx(q):
    return extract_context(q, UNITS)


# ------------------------------------------------------------------ places
def test_exact_district_name_resolves_with_its_province():
    c = ctx("Why is Lahore currently classified as MODERATE?")
    assert c.geography_status == "resolved" and c.admin_unit["name"] == "Lahore" and c.admin_unit["level"] == 2
    assert c.admin_unit["id"] == BY_NAME[(2, "Lahore")]["id"] and c.admin_unit["match_method"] == "exact" and c.admin_unit["province"] == "Punjab"
    assert c.province["name"] == "Punjab" and c.latest_requested and c.risk_intent


def test_known_alias_resolves_and_is_labelled_alias():
    c = ctx("Flood damage reported in DG Khan?")
    assert c.geography_status == "resolved" and c.admin_unit["name"] == "Dera Ghazi Khan" and c.admin_unit["match_method"] == "alias"
    assert c.admin_unit["raw"] == "DG Khan"
    p = ctx("What is the risk in ICT?")
    assert p.admin_unit["name"] == "Islamabad Capital Territory" and p.admin_unit["level"] == 1 and p.admin_unit["match_method"] == "alias"


def test_province_name_resolves_to_a_province_unit_not_a_district():
    c = ctx("Evidence for operational risk in Punjab")
    assert c.admin_unit["level"] == 1 and c.admin_unit["name"] == "Punjab" and c.province == {"id": c.admin_unit["id"], "name": "Punjab"}


def test_ambiguous_name_is_not_guessed():
    c = ctx("Why is Islamabad classified as HIGH risk?")             # alias of the ICT province AND a district name
    assert c.geography_status == "ambiguous" and c.admin_unit is None and c.province is None
    m = c.mentions[0]
    assert m["status"] == "ambiguous" and {x["level"] for x in m["candidates"]} == {1, 2} and m["raw"] == "Islamabad"
    assert any("ambiguous" in n for n in c.notes)


def test_several_different_places_are_not_collapsed_into_one():
    assert ctx("Compare Lahore and Multan").geography_status == "multiple"
    assert ctx("Lahore and Sindh").geography_status == "multiple"                 # the district is not in that province
    c = ctx("Flooding in Lahore, Punjab")
    assert c.geography_status == "resolved" and c.admin_unit["name"] == "Lahore"    # a district and its own province: the district wins


def test_caveated_seed_unit_keeps_the_text_and_is_not_resolved():
    c = ctx("What happened at Fort Munro?")
    assert c.geography_status == "unresolved" and c.admin_unit is None
    assert c.mentions == [{"raw": "Fort Munro", "status": "unresolved", "match_method": "caveated_seed_unit", "candidates": []}]


def test_no_place_and_no_fuzzy_matching():
    assert ctx("What is the monsoon forecast?").geography_status == "not_stated"
    assert ctx("Rain in Lahor").geography_status == "not_stated"                  # a near miss is never accepted
    assert ctx("hurricane damage in Florida").geography_status == "not_stated"


def test_question_words_and_stop_words_never_match_places():
    for q in ("What was the risk on that date?", "Who is at risk in the plains?", "Is it going to rain tomorrow in the north?"):
        assert ctx(q).geography_status == "not_stated"


def test_gauge_station_names_are_not_used():
    assert ctx("What was the discharge at Tarbela Marala Chashma?").geography_status == "not_stated"


# ------------------------------------------------------------------ dates
@pytest.mark.parametrize("q,expect", [
    ("on 2026-07-11", {"date": "2026-07-11"}),
    ("on 12.07.2026", {"date": "2026-07-12"}),                      # day first (CLAUDE.md): 12 July, not 7 December
    ("on 13/07/2026", {"date": "2026-07-13"}),
    ("on 5th July 2026", {"date": "2026-07-05"}),
    ("on July 5, 2026", {"date": "2026-07-05"}),
    ("during July 2026", {"date_from": "2026-07-01", "date_to": "2026-07-31"}),
    ("in February 2028", {"date_from": "2028-02-01", "date_to": "2028-02-29"}),
    ("on 31.02.2026", {"date": None, "date_from": None}),            # impossible date: ignored, never repaired
    ("no date here", {"date": None, "date_from": None}),
])
def test_date_extraction(q, expect):
    d = find_dates(q)
    for k, v in expect.items():
        assert d[k] == v


def test_latest_words():
    assert ctx("current risk in Lahore").latest_requested and ctx("risk in Lahore").latest_requested is False


# ------------------------------------------------------------------ events
def test_event_extraction():
    assert find_events("flash flood in Swat") == ["flash_flood"]                  # not also "flood"
    assert find_events("floods and landslides") == ["flood", "landslide"]
    assert find_events("heavy rainfall") == ["heavy_rainfall"] and find_events("a heat wave") == ["heatwave"]
    assert find_events("GLOF alert") == ["glof"] and find_events("nothing relevant") == []


def test_risk_intent_detection():
    assert ctx("Why is Sialkot classified as MODERATE?").risk_intent
    assert ctx("What is the operational risk in Punjab?").risk_intent
    assert not ctx("What flash floods affected Swat?").risk_intent
