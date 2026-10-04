"""Task 34 -- deterministic intent routing, plans, and geography resolution (existing exact/alias/normalised resolver; no fuzzy matching, no inference)."""

import pytest

from pipeline.agents import contracts as C
from pipeline.agents import geography as agent_geo
from pipeline.agents import router
from scripts.geo.canonical_data import DISTRICTS, PROVINCES

from tests.agents.fakes import UNITS


def canonical_units():
    """Every canonical province and district with synthetic ids (the aliases come from the real canonical data)."""
    units, pid = [], {}
    for i, p in enumerate(PROVINCES, start=1):
        pid[p["name"]] = i
        units.append({"id": i, "level": 1, "name": p["name"], "province": None})
    for j, d in enumerate(DISTRICTS, start=100):
        units.append({"id": j, "level": 2, "name": d["name"], "province": d["province"]})
    return units


CANON = canonical_units()


@pytest.mark.parametrize("q,intent", [
    ("What is the current risk in Lahore?", C.CURRENT_RISK), ("What is the latest risk status of Sialkot?", C.CURRENT_RISK),
    ("What was Lahore's risk status on 2026-07-01?", C.HISTORICAL_RISK), ("What was the risk in Lahore in July 2026?", C.HISTORICAL_RISK),
    ("What did NDMA report about flooding in Sindh?", C.DOCUMENT_SEARCH), ("Any PDMA advisory about heavy rain in Punjab?", C.DOCUMENT_SEARCH),
    ("What is the flood situation in Sindh?", C.DOCUMENT_SEARCH), ("What is the AQI forecast for Lahore?", C.ML_FORECAST), ("Predict the air quality in Lahore tomorrow", C.ML_FORECAST),
    ("Why is Lahore currently classified LOW and is there any AQI forecast?", C.COMBINED_INTELLIGENCE), ("What is Sialkot's risk status and what did NDMA report about floods in Punjab?", C.COMBINED_INTELLIGENCE),
    ("What is Lahore's risk status and its AQI forecast?", C.COMBINED_INTELLIGENCE), ("Why is Sialkot classified as MODERATE?", C.EVIDENCE_GROUNDED_QUESTION),
    ("Which province is Lahore in?", C.GEOGRAPHY_LOOKUP), ("list districts in Punjab", C.GEOGRAPHY_LOOKUP), ("What districts are in Sindh?", C.GEOGRAPHY_LOOKUP),
    ("What is the AQI in Lahore?", C.UNSUPPORTED), ("Tell me a joke", C.UNSUPPORTED), ("hello there", C.UNSUPPORTED),
])
def test_deterministic_intent_routing(q, intent):
    assert router.analyze(q).intent == intent


def test_explicit_date_parameter_makes_a_risk_question_historical():
    assert router.analyze("What is Lahore's risk status?", "2026-07-01").intent == C.HISTORICAL_RISK
    assert router.analyze("What is Lahore's risk status?").intent == C.CURRENT_RISK


def test_routing_is_deterministic_and_needs_no_model():
    q = "Why is Lahore currently classified LOW and is there any AQI forecast?"
    assert [router.analyze(q).to_dict() for _ in range(5)] == [router.analyze(q).to_dict()] * 5


def plan_tools(q, unit_id=30, date=None, province=None):
    a = router.analyze(q, date)
    unit = next(u for u in UNITS if u["id"] == unit_id) if unit_id else None
    prov = {"id": 2, "name": "Punjab"} if unit and unit["province"] == "Punjab" else province
    return a, router.build_plan(a, unit, prov, "hybrid", 5)


@pytest.mark.parametrize("q,date,tools", [
    ("What is the current risk in Lahore?", None, ["risk.latest"]), ("What was Lahore's risk status on 2026-07-01?", None, ["risk.on_date"]),
    ("What was Lahore's risk in July 2026?", None, ["risk.history"]), ("What is the AQI forecast for Lahore?", None, ["ml.predictions"]),
    ("What did NDMA report about flooding in Punjab?", None, ["rag.retrieve"]), ("Why is Lahore currently classified LOW and is there any AQI forecast?", None, ["risk.latest", "rag.retrieve", "ml.predictions"]),
    ("What is Lahore's risk status and its AQI forecast?", None, ["risk.latest", "ml.predictions"]), ("What is Lahore's risk status and what did NDMA report?", None, ["risk.latest", "rag.retrieve"]),
    ("Why is Lahore classified LOW?", None, ["intelligence.ask"]), ("What is the weather forecast for Lahore tomorrow?", None, ["ml.models"]),
    ("What are the coverage and confidence of the latest risk in Lahore?", None, ["risk.latest", "risk.coverage"])])
def test_plans_select_the_expected_tools(q, date, tools):
    a, plan = plan_tools(q, date=date)
    assert [c.tool for c in plan] == tools
    assert all(c.origin == "deterministic" for c in plan)


def test_plan_arguments_carry_only_resolved_values():
    a, plan = plan_tools("What was Lahore's risk status on 2026-07-01?")
    assert plan[0].arguments == {"admin_unit_id": 30, "date": "2026-07-01"}
    a, plan = plan_tools("What did NDMA report about flooding in Sindh?", unit_id=None, province={"id": 3, "name": "Sindh"})
    args = plan[0].arguments
    assert args["province"] == "Sindh" and args["source"] == "ndma" and args["event_type"] == "flood" and "admin_unit_id" not in args


def test_forecast_horizon_and_target_extraction():
    assert router.analyze("AQI forecast for Lahore tomorrow").horizon == 1
    assert router.analyze("AQI forecast for Lahore in 3 days").horizon == 3
    assert router.analyze("Lahore AQI forecast next week").horizon == 7
    assert router.analyze("AQI forecast for Lahore").horizon is None
    assert router.analyze("AQI forecast for Lahore").forecast_target == "air_quality_index"
    assert router.analyze("rainfall forecast for Lahore").forecast_target == "unsupported:rainfall"


def test_premise_check_uses_the_engine_value():
    rec = {"risk_status": "LOW", "risk_date": "2026-09-15"}
    assert router.analyze("Why is Lahore classified HIGH?").stated_status == "HIGH"
    assert router.analyze("Why is Lahore classified as high?").stated_status == "HIGH"
    p = router.premise_check("HIGH", rec)
    assert p["matches"] is False and p["engine_status"] == "LOW" and "LOW" in p["note"]
    assert router.premise_check("LOW", rec)["matches"] is True
    assert router.premise_check(None, rec) is None and router.premise_check("HIGH", None) is None


# ---------------------------------------------------------------------------------------------------------------------------------- geography
def resolve(text, units=CANON):
    return agent_geo.resolve_place(text, units)


def test_exact_province_and_district_match():
    r = resolve("What is the risk in Lahore?")
    assert r["status"] == "resolved" and r["unit"]["name"] == "Lahore" and r["unit"]["match_method"] == "exact" and r["province"]["name"] == "Punjab"
    r = resolve("risk in Sindh")
    assert r["status"] == "resolved" and r["unit"]["level"] == 1 and r["unit"]["name"] == "Sindh"


def test_alias_matches_use_the_canonical_alias_lists():
    r = resolve("flooding in ICT")
    assert r["status"] == "resolved" and r["unit"]["name"] == "Islamabad Capital Territory" and r["unit"]["match_method"] == "alias"
    r = resolve("flooding in Gilgit Baltistan")
    assert r["unit"]["name"] == "Gilgit-Baltistan"
    assert resolve("flooding in KP")["unit"] is None                # two-letter aliases are ignored in free text by the existing resolver (kept: no new matching)
    r = resolve("risk in DG Khan")
    assert r["unit"]["name"] == "Dera Ghazi Khan" and r["unit"]["match_method"] == "alias"
    r = resolve("risk in R.Y. Khan")
    assert r["unit"]["name"] == "Rahim Yar Khan"


def test_islamabad_is_ambiguous_and_returns_its_candidate_interpretations():
    r = resolve("What is Islamabad's risk status?")
    assert r["status"] == "ambiguous" and r["unit"] is None and r["province"] is None
    got = {(c["name"], c["level"]) for c in r["candidates"]}
    assert got == {("Islamabad Capital Territory", 1), ("Islamabad", 2)}
    assert r["notes"] and "ambiguous" in r["notes"][0]


def test_unresolved_and_unrecognised_places_are_never_guessed():
    r = resolve("What is the risk in Kabul?")
    assert r["unit"] is None and r["status"] == "not_stated" and r["unrecognized_places"] == ["Kabul"]
    r = resolve("What is the risk in Pakistan?")
    assert r["unit"] is None and r["unrecognized_places"] == ["Pakistan"]
    r = resolve("What is the risk at Marala Barrage?")
    assert r["unit"] is None and r["unrecognized_places"] == ["Marala Barrage"]


@pytest.mark.parametrize("text", ["risk in Lahor", "risk in Lahoore", "risk in Sialkott", "risk in Punjab Provence", "risk in Karachee", "risk in Multaan"])
def test_no_fuzzy_matching_of_misspelt_places(text):
    r = resolve(text)
    assert r["unit"] is None or r["unit"]["name"] in ("Punjab",), (text, r["unit"])
    if r["unit"] is None:
        assert r["unrecognized_places"], text                           # the unknown spelling is surfaced, not silently mapped


def test_rivers_gauges_and_tehsils_are_not_mapped_to_districts():
    for text in ("What is the risk at Tarbela?", "risk near the Indus river", "risk in Saddar tehsil"):
        r = resolve(text)
        assert r["unit"] is None, (text, r["unit"])


def test_two_different_places_are_not_collapsed_into_one():
    r = resolve("risk in Lahore and Sialkot")
    assert r["status"] == "multiple" and r["unit"] is None and {c["name"] for c in r["candidates"]} == {"Lahore", "Sialkot"}


def test_recognised_places_are_not_reported_as_unrecognised():
    assert router.unrecognized_places("What did NDMA report about flooding in Sindh?", resolve("flooding in Sindh")["mentions"]) == []
    assert router.unrecognized_places("risk in Lahore in July 2026", resolve("risk in Lahore")["mentions"]) == []
    assert router.unrecognized_places("AQI forecast for Lahore on Monday", resolve("forecast for Lahore")["mentions"]) == []
