import copy
import json
from pathlib import Path

import pytest

from pipeline.geo.gauge_mapping import apply_to_gauge_rows, before_after, build_mapping, top_unresolved
from pipeline.geo.gauge_station import build_inventory, match_key, normalize_station_name
from pipeline.risk.config import load_config
from pipeline.risk.engine import run_engine
from scripts.geo.run_gauge_geography import load_evidence, main as run_main, validate
from tests.risk._helpers import days, gold

REPO = Path(__file__).resolve().parents[2]
UNITS = {"Sialkot": {"id": 10, "level": 2, "province": "Punjab"}, "Mangla": {"id": 33, "level": 2, "province": "Punjab"},
         "Swabi": {"id": 90, "level": 2, "province": "Khyber Pakhtunkhwa"}, "Haripur": {"id": 91, "level": 2, "province": "Khyber Pakhtunkhwa"},
         "Jhang": {"id": 12, "level": 2, "province": "Punjab"}}
CAVEATED = {"Mangla"}


def row(station, river="CHENAB", date="2026-07-01", value=100.0, admin=None, status="unresolved"):
    return {"station_name": station, "location_original": station, "river_name": river, "date": date, "discharge_avg": value,
            "admin_unit_id": admin, "resolution_status": status, "observation_time_basis": "source_observed",
            "provenance": {"sources": [{"source": "pdma", "source_record_id": f"{station}:{date}"}]}}


def cfg(stations):
    return {"mapping_version": "t-1", "mapping_date": "2026-01-01", "validation_status": "pending_manual_review", "stations": stations}


def ev(admin, cls="secondary", source="s", record="r"):
    return {"class": cls, "admin_unit": admin, "source": source, "record": record}


def build(rows, stations):
    inv = build_inventory(rows)
    return inv, build_mapping(inv, cfg(stations), UNITS, CAVEATED)


def by(m, key):
    return next(x for x in m if x["station_key"] == key)


def test_inventory_has_one_unique_record_per_station():
    rows = [row("Marala"), row("Marala", date="2026-07-02"), row("Khanki")]
    inv = build_inventory(rows)
    assert [s["station_key"] for s in inv] == ["pdma:khanki", "pdma:marala"]
    assert by(inv, "pdma:marala")["observation_count"] == 2


def test_station_name_normalization_and_alias_variants_merge():
    assert normalize_station_name("  G.S.  Wala ") == "gs wala"
    assert match_key("G.S. Wala") == match_key("G.S.Wala") == match_key("GS WALA")
    inv = build_inventory([row("G.S. Wala", "SUTLEJ"), row("G.S.Wala", "SUTLEJ")])
    assert len(inv) == 1 and inv[0]["source_name_variants"] == ["G.S. Wala", "G.S.Wala"]


def test_same_name_on_different_rivers_is_not_merged_and_never_cross_mapped():
    rows = [row("Kaha", "RAVI"), row("Kaha", "INDUS")]
    inv = build_inventory(rows)
    assert len(inv) == 2 and len({s["station_key"] for s in inv}) == 2
    mapping = build_mapping(inv, cfg({"Kaha": [ev("Sialkot", "authoritative")]}), UNITS, CAVEATED)
    assert all(m["mapping_status"] == "resolved_authoritative" for m in mapping)   # evidence is by name only; both listed
    mapped = apply_to_gauge_rows(rows, mapping, inv)
    assert {r["river_name"]: r["station_key"] for r in mapped} == {"RAVI": "pdma:kaha:ravi", "INDUS": "pdma:kaha:indus"}


def test_no_fabricated_coordinates_station_ids_or_basin():
    s = build_inventory([row("Marala")])[0]
    assert s["latitude"] is None and s["longitude"] is None and s["source_station_id"] is None
    assert s["basin_name"] is None and s["catchment_name"] is None and s["basin_context_status"] == "unresolved"


def test_authoritative_mapping_keeps_provenance_and_is_eligible():
    inv, m = build([row("Marala")], {"Marala": [ev("Sialkot", "authoritative", "WAPDA", "doc p3")]})
    x = m[0]
    assert (x["mapping_status"], x["mapping_basis"], x["mapping_confidence"]) == ("resolved_authoritative", "authoritative_source", "high")
    assert x["mapping_source"] == "WAPDA" and "doc p3" in x["mapping_source_record"] and x["admin_unit_id"] == 10
    assert x["eligible_for_admin_risk"] and x["ineligibility_reason"] is None


def test_inferred_mapping_is_never_authoritative_or_eligible():
    inv, m = build([row("Marala")], {"Marala": [ev("Sialkot", "secondary")]})
    x = m[0]
    assert x["mapping_status"] == "resolved_inferred" and x["mapping_basis"] == "inferred" and x["mapping_confidence"] == "low"
    assert x["admin_unit_id"] == 10 and not x["eligible_for_admin_risk"] and x["ineligibility_reason"]


def test_unresolved_station_has_null_geography_but_keeps_hydrographic_context():
    inv, m = build([row("Chashma", "INDUS")], {})
    x = m[0]
    assert x["mapping_status"] == "unresolved" and x["admin_unit_id"] is None and not x["eligible_for_admin_risk"]
    assert inv[0]["river_name"] == "Indus" and inv[0]["river_context_status"] == "source_reported"


def test_conflicting_evidence_is_ambiguous_and_picks_nothing():
    inv, m = build([row("Tarbela", "INDUS")], {"Tarbela": [ev("Swabi"), ev("Haripur")]})
    x = m[0]
    assert x["mapping_status"] == "ambiguous" and x["admin_unit_id"] is None and not x["eligible_for_admin_risk"]
    assert "Swabi" in x["caveat"] and "Haripur" in x["caveat"]


def test_duplicate_evidence_for_the_same_unit_does_not_create_duplicate_mappings():
    inv, m = build([row("Marala")], {"Marala": [ev("Sialkot"), ev("Sialkot", "authoritative")]})
    assert len(m) == 1 and m[0]["admin_unit_id"] == 10


def test_evidence_naming_a_unit_missing_from_canonical_geography_stays_unresolved():
    inv, m = build([row("Zed")], {"Zed": [ev("Atlantis", "authoritative")]})
    assert m[0]["mapping_status"] == "unresolved" and m[0]["admin_unit_id"] is None and not m[0]["eligible_for_admin_risk"]


def test_mangla_caveat_is_preserved_not_removed_to_gain_coverage():
    rows = [row("Mangla", "JHELUM", admin=33, status="resolved")]
    inv, m = build(rows, {"Mangla": [ev("Mangla", "legacy"), ev("Mirpur", "secondary")]})
    x = m[0]
    assert x["mapping_status"] == "caveated" and not x["eligible_for_admin_risk"] and x["ineligibility_reason"] == "caveated_geography"
    assert "not a real district" in x["caveat"] and "Mirpur" in x["caveat"]
    assert inv[0]["river_name"] == "Jhelum"          # hydrographic location stays primary
    mapped = apply_to_gauge_rows(rows, m, inv)
    assert mapped[0]["resolution_status"] == "unresolved" and mapped[0]["admin_unit_id"] is None


def test_unresolved_observations_are_preserved_with_a_reason_and_inputs_not_mutated():
    rows = [row("Chashma", "INDUS"), row("Unknown Site", "NULLAHS")]
    snapshot = copy.deepcopy(rows)
    inv, m = build(rows, {})
    mapped = apply_to_gauge_rows(rows, m, inv)
    assert rows == snapshot and len(mapped) == len(rows)
    assert all(r["resolution_status"] == "unresolved" and r["geography_unresolved_reason"] for r in mapped)
    assert [r["discharge_avg"] for r in mapped] == [100.0, 100.0]


def test_legacy_gold_resolution_is_not_trusted_without_an_eligible_mapping():
    rows = [row("Marala", admin=10, status="resolved")]
    inv, m = build(rows, {})
    assert apply_to_gauge_rows(rows, m, inv)[0]["admin_unit_id"] is None


def test_risk_engine_only_consumes_eligible_mappings():
    dates = days("2026-05-01", 45)
    rows = [row("Marala", date=d, value=100.0 + i) for i, d in enumerate(dates)]
    rows += [row("Khanki", date=d, value=100.0 + i) for i, d in enumerate(dates)]
    rows += [row("Mangla", "JHELUM", date=d, value=100.0 + i) for i, d in enumerate(dates)]
    inv, m = build(rows, {"Marala": [ev("Sialkot", "authoritative", "WAPDA", "x")], "Khanki": [ev("Jhang", "secondary")],
                          "Mangla": [ev("Mangla", "legacy")]})
    out = run_engine(gold(gauge=apply_to_gauge_rows(rows, m, inv)), load_config())
    assert {r["admin_unit_id"] for r in out["rows"]} == {10}                    # only the eligible mapping
    assert all(r["signal_states"]["gauge"] != "MISSING" for r in out["rows"])
    unresolved_stations = {u.get("station_name") for u in out["unresolved"]}
    assert {"Khanki", "Mangla"} <= unresolved_stations                        # preserved, not dropped


def test_mapping_change_does_not_leak_into_earlier_dates():
    dates = days("2026-05-01", 45)
    rows = [row("Marala", date=d, value=100.0 + i) for i, d in enumerate(dates)]
    inv, m = build(rows, {"Marala": [ev("Sialkot", "authoritative", "WAPDA", "x")]})
    full = run_engine(gold(gauge=apply_to_gauge_rows(rows, m, inv)), load_config())["rows"]
    cut = run_engine(gold(gauge=apply_to_gauge_rows(rows[:30], m, inv)), load_config())["rows"]
    assert [r for r in full if r["date"] <= dates[29]] == cut                  # later observations never change earlier rows


def test_before_after_counts_observations_not_aliases():
    rows = [row("Mangla", "JHELUM", date=d, admin=33, status="resolved") for d in days("2026-07-01", 3)] + [row("Marala")]
    inv, m = build(rows, {"Mangla": [ev("Mangla", "legacy")]})
    mapped = apply_to_gauge_rows(rows, m, inv)
    metrics = {x["metric"]: x for x in before_after(rows, mapped, inv, m, caveated_unit_ids={33})}
    assert metrics["observations_with_candidate_admin_geography"]["before_task24"] == 3
    assert metrics["observations_attributable_for_risk"]["after_task24"] == 0
    assert metrics["observations_unresolved_for_risk"]["after_task24"] == 4
    assert metrics["caveated_stations"]["after_task24"] == 1
    assert all(x["change"] == x["after_task24"] - x["before_task24"] for x in metrics.values())


def test_top_unresolved_is_ordered_by_observation_count():
    rows = [row("A")] * 1 + [row("B", date=d) for d in days("2026-07-01", 3)]
    inv, m = build(rows, {})
    assert [t["station_key"] for t in top_unresolved(m, inv)] == ["pdma:b", "pdma:a"]


def test_mapping_is_deterministic_idempotent_and_versioned():
    rows = [row("Marala"), row("Khanki"), row("Tarbela", "INDUS")]
    a = build(rows, {"Marala": [ev("Sialkot")]})[1]
    b = build(list(reversed(rows)), {"Marala": [ev("Sialkot")]})[1]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert all(x["mapping_version"] == "t-1" and x["mapping_date"] and x["validation_status"] == "pending_manual_review" for x in a)


def test_validate_flags_eligible_without_evidence_and_fabricated_coordinates():
    inv, m = build([row("Marala")], {})
    bad_inv = copy.deepcopy(inv)
    bad_inv[0]["latitude"] = 32.0
    m[0]["eligible_for_admin_risk"] = True
    errs = validate(bad_inv, m)
    assert any("coordinates" in e for e in errs) and any("eligible without sufficient evidence" in e for e in errs)


def test_real_evidence_file_is_versioned_and_never_marks_secondary_evidence_authoritative():
    c = load_evidence()
    assert c["mapping_version"] and c["mapping_date"] and c["validation_status"] == "pending_manual_review"
    for station, entries in c["stations"].items():
        assert all(e["source"] and e["record"] and e["class"] in {"authoritative", "secondary", "legacy", "source_reported"} for e in entries), station
    assert not any(e["class"] == "authoritative" for es in c["stations"].values() for e in es)   # none located so far


GOLD = REPO / "data" / "analytics" / "gold" / "datasets" / "gold_gauge_daily.jsonl"


@pytest.mark.skipif(not GOLD.exists(), reason="Gold gauge dataset not generated in this environment")
def test_real_data_run_is_valid_and_idempotent(tmp_path):
    first = run_main()
    first_files = {p.name: p.read_bytes() for p in (REPO / "data" / "analytics" / "geo").glob("gauge_*.json")}
    second = run_main()
    second_files = {p.name: p.read_bytes() for p in (REPO / "data" / "analytics" / "geo").glob("gauge_*.json")}
    assert first["validation_errors"] == [] and first == second and first_files == second_files
    inv = json.loads(first_files["gauge_station_inventory.json"])
    assert len({s["station_key"] for s in inv}) == len(inv) == first["distinct_stations"]
    assert first["coordinate_based_mappings"] == 0
