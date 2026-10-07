"""Task 38 -- authoritative gauge station evidence: the position-uncertainty probe (synthetic geometry), the real evidence registry, the committed
mapping/coverage outputs, and the guarantee that newly eligible signals never produce a score."""

import json
from pathlib import Path

import yaml

from pipeline.geo.boundaries import BoundaryIndex, build_crosswalk, crosswalk_lookup, locate_within_radius
from pipeline.geo.coverage_evidence import gauge_station_view, secondary_never_eligible
from pipeline.geo.gauge_mapping import build_mapping
from pipeline.geo.gauge_station import build_inventory
from pipeline.risk import scoring_v2 as S
from tests.geo.test_boundaries import SRC, canon, coord_ev, coord_map, square, unit
from tests.geo.test_gauge_station_mapping import CAVEATED, UNITS, row

ROOT = Path(__file__).resolve().parents[2]
GEO = ROOT / "data" / "analytics" / "geo"
EVID = yaml.safe_load((ROOT / "config" / "gauge_station_evidence.yaml").read_text(encoding="utf-8"))
MAPPING = {m["station_name"]: m for m in json.loads((GEO / "gauge_station_mapping.json").read_text(encoding="utf-8"))}
COVER = json.loads((GEO / "gauge_geography_coverage.json").read_text(encoding="utf-8"))
AUDIT = json.loads((GEO / "coverage_evidence_audit.json").read_text(encoding="utf-8"))


def two_district_index():
    """Two adjacent synthetic districts split at lon 74.5 (~111 km per degree of latitude; 1 degree of lon ~ 94 km at 32.5 N)."""
    return BoundaryIndex([unit(1, "P1", "Punjab", [square(70, 28, 76, 34)]),
                          unit(2, "D1", "Sialkot", [square(74, 32, 74.5, 33)], "P1"),
                          unit(2, "D2", "Zeta", [square(74.5, 32, 75, 33)], "P1")], SRC, "crs84")


# --- the probe -----------------------------------------------------------------------------------------------------------------
def test_probe_is_stable_when_the_whole_disc_is_inside_one_district():
    idx = two_district_index()
    r = locate_within_radius(idx, crosswalk_lookup(build_crosswalk(idx, canon(), {})), 32.5, 74.25, 1000)
    assert r["stable"] and r["pori_admin_unit_name"] == "Sialkot" and r["probe_units"] == ["D1"]


def test_probe_refuses_a_point_near_a_district_line():
    idx = two_district_index()
    near = 74.5 - 0.004                           # ~375 m west of the line: centre is inside Sialkot, a 1 km disc is not
    assert locate_within_radius(idx, {}, 32.5, near, 100)["stable"]
    r = locate_within_radius(idx, {}, 32.5, near, 1000)
    assert not r["stable"] and set(r["probe_units"]) == {"D1", "D2"}


def test_probe_refuses_a_disc_that_leaves_every_polygon():
    idx = two_district_index()
    r = locate_within_radius(idx, {}, 32.01, 74.25, 5000)
    assert not r["stable"] and "outside/overlap" in r["probe_units"]


def test_unstable_coordinate_evidence_never_becomes_an_eligible_mapping():
    e = {**coord_ev("authoritative", lat=32.5, lon=74.4999), "position_uncertainty_m": 1000}
    idx = two_district_index()
    inv = build_inventory([row("Marala")])
    cw = crosswalk_lookup(build_crosswalk(idx, canon(), {}))
    m = build_mapping(inv, {"mapping_version": "t", "mapping_date": "d", "evidence": [e]}, UNITS | {"Sialkot": {"id": 10, "level": 2, "province": "Punjab"}},
                      CAVEATED, idx, cw, {"allow_coordinate_derived_eligibility": True})[0]
    assert not m["eligible_for_admin_risk"] and m["mapping_status"] == "unresolved" and "not stable" in m["caveat"]
    assert m["boundary_unit_name"] is None                       # the unstable attribution is not recorded
    assert len(m["evidence"]) == 1 and m["evidence"][0]["position_uncertainty_m"] == 1000     # the evidence itself is preserved


def test_stable_coordinate_with_uncertainty_is_eligible_and_labelled_coordinate_based():
    e = {**coord_ev("authoritative", lat=32.5, lon=74.25), "position_uncertainty_m": 1000}
    _, m = coord_map([e])
    assert m[0]["eligible_for_admin_risk"] and m[0]["geography_derivation"] == "coordinate_based" and m[0]["mapping_status"] == "resolved_coordinate"


def test_coordinate_without_uncertainty_keeps_the_task25_behaviour():
    _, m = coord_map([coord_ev("authoritative")])
    assert m[0]["mapping_status"] == "resolved_coordinate"


# --- the real registry ---------------------------------------------------------------------------------------------------------
AUTH = [e for e in EVID["evidence"] if e["evidence_status"] == "authoritative"]


def test_every_authoritative_record_is_fully_traceable():
    assert {e["station_name"] for e in AUTH} == {"Chashma", "Tarbela", "Rasul", "Marala", "Khanki", "Qadirabad", "Trimmu", "Panjnad", "Balloki", "Sidhnai", "Suleimanki", "Islam"}
    for e in AUTH:
        for f in ("source_title", "source_organization", "source_page", "station_name_in_source", "source_url", "source_statement", "source_record", "retrieved", "notes"):
            assert e.get(f), (e["station_name"], f)
        assert e["source_type"] == "official" and e["source_url"].startswith("https://")
        assert e.get("district") or (e.get("latitude") is not None and e.get("position_uncertainty_m"))


def test_coordinates_come_only_with_a_stated_position_uncertainty_and_are_not_invented():
    pid = [e for e in AUTH if e.get("latitude") is not None]
    assert len(pid) == 10 and all(e["position_uncertainty_m"] in (1000, 1500, 2000, 2500, 4000, 5000, 5500, 6000, 6500) for e in pid)
    assert all("breaching section" in e["source_statement"] for e in pid)
    assert not any(e.get("latitude") is not None for e in EVID["evidence"] if e["evidence_status"] != "authoritative")
    assert {d["station_name"] for d in EVID["deferred_official_coordinates"]} == {"Shahdara", "Kalabagh"}
    assert not any(e["station_name"] in ("Shahdara", "Kalabagh") for e in EVID["evidence"])     # deferred coordinates are not evidence records


def test_investigation_log_records_what_was_and_was_not_retrievable():
    log = {i["source"]: i for i in EVID["investigation_log"]}
    assert any("Flood Report 2025" in k and i["result"] == "authoritative_coordinates_with_uncertainty" for k, i in log.items())
    assert any("Chashma" in k and i["result"] == "authoritative_district" for k, i in log.items())
    assert any("Tarbela" in k and i["result"] == "authoritative_district_not_in_canonical" for k, i in log.items())
    assert any("ffc.gov.pk" in k and i["result"] == "unreachable" for k, i in log.items())
    assert all(i["outcome"] and i["checked"] for i in EVID["investigation_log"])


# --- the committed outcome -----------------------------------------------------------------------------------------------------
def test_exactly_two_stations_are_eligible_and_both_are_evidence_backed():
    elig = {n for n, m in MAPPING.items() if m["eligible_for_admin_risk"]}
    assert elig == {"Chashma", "Trimmu"}
    c, t = MAPPING["Chashma"], MAPPING["Trimmu"]
    assert c["mapping_status"] == "resolved_authoritative" and c["admin_unit_name"] == "Mianwali" and c["geography_derivation"] == "source_reported"
    assert t["mapping_status"] == "resolved_coordinate" and t["admin_unit_name"] == "Jhang" and t["geography_derivation"] == "coordinate_based"
    assert t["mapping_confidence"] == "medium" and any(e["position_uncertainty_m"] == 5500 for e in t["evidence"])


def test_canonical_ids_of_the_mapped_units_are_the_existing_ones():
    xw = json.loads((GEO / "gauge_boundary_crosswalk.json").read_text(encoding="utf-8"))["crosswalk"]
    ids = {c["pori_admin_unit_name"]: c["pori_admin_unit_id"] for c in xw if c["boundary_level"] == 2 and c["pori_admin_unit_id"]}
    assert MAPPING["Chashma"]["admin_unit_id"] == ids["Mianwali"] and MAPPING["Trimmu"]["admin_unit_id"] == ids["Jhang"]


def test_conflicts_are_still_conflicts_and_tarbela_swabi_is_preserved_but_not_applied():
    assert MAPPING["Tarbela"]["mapping_status"] == "ambiguous" and MAPPING["Rasul"]["mapping_status"] == "ambiguous"
    assert not MAPPING["Tarbela"]["eligible_for_admin_risk"] and MAPPING["Tarbela"]["admin_unit_id"] is None
    tarbela = {e["district"]: e["evidence_status"] for e in MAPPING["Tarbela"]["evidence"]}
    assert tarbela["Swabi"] == "authoritative" and tarbela["Haripur"] == "secondary"
    from scripts.geo.canonical_data import DISTRICTS
    assert "Swabi" not in {d["name"] for d in DISTRICTS}                   # applying it would need a canonical-model change


def test_unstable_official_coordinates_leave_the_other_stations_ineligible_with_a_reason():
    for n in ("Rasul", "Marala", "Khanki", "Qadirabad", "Panjnad", "Sidhnai", "Suleimanki", "Islam", "Balloki"):
        m = MAPPING[n]
        assert not m["eligible_for_admin_risk"]
        assert "not stable within" in m["caveat"] or "no canonical match" in m["caveat"], n
        assert any(e["latitude"] is not None for e in m["evidence"])        # the official evidence stays on the record


def test_secondary_only_stations_are_unchanged_and_never_eligible():
    v = gauge_station_view(list(MAPPING.values()))
    assert {r["station_name"] for r in v["secondary_only"]} == {"Marala", "Khanki", "Balloki"} and secondary_never_eligible(v)
    assert MAPPING["Mangla"]["mapping_status"] == "caveated" and {r["station_name"] for r in v["caveated"]} == {"Mangla"}
    assert len(v["unresolved"]) == 33 and len(v["conflicting"]) == 2 and len(v["resolved"]) == 2 and len(v["eligible"]) == 2


def test_hill_torrent_and_nullah_stations_have_no_evidence_and_stay_unresolved():
    for n in ("Aik", "Deg", "Bein", "Palkhu", "Basanter", "Zangi", "Kaha", "Sanghar", "Vehova", "Kaura", "Lai"):
        assert MAPPING[n]["mapping_status"] == "unresolved" and not MAPPING[n]["evidence"], n


# --- coverage impact -----------------------------------------------------------------------------------------------------------
def test_coverage_numbers_are_internally_consistent():
    assert COVER["eligible_stations"] == 2 and COVER["observations_eligible_for_risk"] == 186 and COVER["observations_unresolved"] == 3500
    assert COVER["authoritative_station_mappings"] == 1 and COVER["coordinate_derived_mappings"] == 1      # Chashma (district statement) + Trimmu (coordinates)
    assert COVER["mapping_status_counts"] == {"ambiguous": 2, "caveated": 1, "resolved_authoritative": 1, "resolved_coordinate": 1, "resolved_inferred": 3, "unresolved": 33}
    g = AUDIT["gauge_stations"]
    assert g["authoritative_mappings"] == 2 and g["baseline_authoritative_mappings_task37"] == 0 and g["observations_with_eligible_mapping"] == 186
    assert 3686 == g["observations"]


def test_newly_eligible_observations_are_exactly_the_post_history_ones():
    # two stations x 93 daily observations; the first 30 of each lack the 30 prior observations the contract needs
    assert AUDIT["newly_unlocked_eligible_observations"]["gauge"] == 2 * (93 - 30) == 126
    assert all(v == 0 for k, v in AUDIT["newly_unlocked_eligible_observations"].items() if k != "gauge")
    d = AUDIT["domains"]["gauge"]
    assert d["eligibility_counts_before"] == {"UNRESOLVED_GEOGRAPHY": 3499} and d["eligibility_counts_after"]["ELIGIBLE"] == 126
    assert d["eligibility_counts_after"]["INSUFFICIENT_DATA"] == 60 and d["admin_units_with_eligible_observation"] == 2
    c = AUDIT["cells"]
    assert c["with_an_eligible_signal_group_after"] - c["with_an_eligible_signal_group_before"] == 126
    assert c["with_two_independent_groups_before"] == c["with_two_independent_groups_after"] == 8      # no new multi-group cell


def test_newly_eligible_gauge_signals_still_abstain_and_never_score():
    o = {"domain": "gauge", "unit": 1, "cell_date": "2026-08-01", "obs_date": "2026-08-01", "value": 5.0, "normalized": 0.7, "history_count": 40,
         "geography_status": "resolved", "geography_caveat": False, "source": "pdma", "source_record_ids": ["r"]}
    cell = S.assess_cell([o], S.SERVING_CONFIG)
    assert cell["eligible_signal_count"] == 1 and cell["risk_score"] is None and cell["score_status"] == S.ABSTAINED
    assert S.R_DISABLED in cell["abstention_reasons"] and S.SERVING_CONFIG["enabled"] is False and S.SERVING_CONFIG["weights"] == {}
    assert AUDIT["scoring_enabled"] is False and AUDIT["cells_scored"] == 0 and AUDIT["score_v2_outcome"] == "B"
    rows = [json.loads(x) for x in (ROOT / "data" / "analytics" / "risk" / "gold_operational_risk.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 1771 and all(r["risk_score"] is None for r in rows)
