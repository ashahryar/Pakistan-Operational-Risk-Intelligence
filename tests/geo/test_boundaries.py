"""Boundary foundation + coordinate evidence tests. Geometry fixtures are small, clearly-synthetic squares that
test the algorithms; they are never presented as real Pakistani boundaries. Real-boundary checks run against the
downloaded HDX file and skip if it is absent."""

import json
from pathlib import Path

import pytest

from pipeline.geo.boundaries import (
    BoundaryIndex,
    build_crosswalk,
    crosswalk_lookup,
    find_duplicate_coordinates,
    load_geojson_units,
    load_index,
    locate_station,
    validate_coordinate,
    validate_index,
)
from pipeline.geo.gauge_mapping import apply_to_gauge_rows, build_mapping
from pipeline.geo.gauge_station import build_inventory
from pipeline.risk.config import load_config
from pipeline.risk.engine import run_engine
from scripts.geo.run_gauge_geography import load_boundary_cfg, validate
from tests.geo.test_gauge_station_mapping import CAVEATED, UNITS, cfg, row
from tests.risk._helpers import days, gold

REPO = Path(__file__).resolve().parents[2]


def square(x0, y0, x1, y1):
    return [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]


def unit(level, pcode, name, polys, parent=None):
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    return {"level": level, "pcode": pcode, "name": name, "parent_pcode": parent, "polygons": polys,
            "bbox": (min(xs), min(ys), max(xs), max(ys)), "multipart": len(polys) > 1, "version": "v", "valid_on": "d"}


SRC = {"dataset": "SYN", "version": "v0", "accepted_for_coordinate_mapping": True}


DONUT = [[[70, 28], [72, 28], [72, 30], [70, 30], [70, 28]],          # outer ring
         [[70.5, 28.5], [71.5, 28.5], [71.5, 29.5], [70.5, 29.5], [70.5, 28.5]]]   # hole


def synth_index():
    units = [unit(1, "P1", "Punjab", [square(70, 28, 76, 34)]),
             unit(2, "D1", "Sialkot", [square(74, 32, 75, 33)], "P1"),
             unit(2, "D2", "Zeta", [square(72, 30, 73, 31)], "P1"),
             unit(2, "D3", "Donut", [DONUT], "P1")]
    return BoundaryIndex(units, SRC, "crs84")


def canon():
    return [{"id": 1, "name": "Punjab", "level": 1, "province": "Punjab", "aliases": []},
            {"id": 10, "name": "Sialkot", "level": 2, "province": "Punjab", "aliases": []}]


# ------------------------------------------------------------- coordinate validation
def test_valid_pakistan_coordinate_passes():
    assert validate_coordinate(32.51234, 74.56789) == {"valid": True, "flags": []}


def test_reversed_coordinates_are_detected_not_repaired():
    v = validate_coordinate(74.5, 32.5)                 # lat/lon swapped
    assert not v["valid"] and "likely_reversed" in v["flags"]


def test_out_of_range_non_numeric_and_foreign_coordinates_rejected():
    assert "out_of_range" in validate_coordinate(120.0, 74.0)["flags"]
    assert validate_coordinate("x", 74)["flags"] == ["not_numeric"]
    assert validate_coordinate(float("nan"), 74)["flags"] == ["not_finite"]
    assert "outside_pakistan_plausible_extent" in validate_coordinate(51.5, -0.1)["flags"]   # London


def test_low_precision_is_flagged_but_valid():
    v = validate_coordinate(32.0, 74.0)
    assert v["valid"] and v["flags"] == ["low_precision"]


def test_duplicate_coordinates_across_stations_detected():
    recs = [{"station_key": "a", "latitude": 32.123456, "longitude": 74.1}, {"station_key": "b", "latitude": 32.123456, "longitude": 74.1},
            {"station_key": "c", "latitude": 31.0, "longitude": 74.0}]
    assert find_duplicate_coordinates(recs) == {(32.123456, 74.1): ["a", "b"]}


# ------------------------------------------------------------- point in polygon
def test_point_inside_one_district():
    r = synth_index().locate(32.5, 74.5, 2)
    assert r["status"] == "inside" and [m["pcode"] for m in r["matches"]] == ["D1"]


def test_station_outside_all_polygons():
    assert synth_index().locate(10.0, 10.0, 2) == {"status": "outside", "matches": []}
    assert synth_index().locate(33.5, 71.0, 2)["status"] == "outside"       # inside province, in no district


def test_point_on_boundary_is_ambiguous_not_guessed():
    assert synth_index().locate(32.5, 74.0, 2)["status"] == "on_boundary"   # exactly on Sialkot's west edge
    assert synth_index().locate(32.0, 74.0, 2)["status"] == "on_boundary"   # a vertex


def test_hole_is_outside_the_polygon():
    idx = synth_index()
    assert idx.locate(29.0, 71.0, 2)["status"] == "outside"                  # inside the hole
    assert idx.locate(29.0, 70.2, 2)["status"] == "inside"                   # in the ring body


def test_overlapping_polygons_report_multiple():
    idx = BoundaryIndex([unit(2, "A", "A", [square(0, 0, 2, 2)]), unit(2, "B", "B", [square(1, 1, 3, 3)])], SRC, "crs84")
    assert idx.locate(1.5, 1.5, 2)["status"] == "multiple"


def test_multipart_geometry_is_supported():
    u = unit(2, "M", "Multi", [square(0, 0, 1, 1), square(5, 5, 6, 6)])
    idx = BoundaryIndex([u], SRC, "crs84")
    assert idx.locate(5.5, 5.5, 2)["status"] == "inside" and idx.locate(3, 3, 2)["status"] == "outside"


# ------------------------------------------------------------- geometry / CRS validation
def write_geojson(path, crs, feats):
    d = {"type": "FeatureCollection", "features": feats}
    if crs:
        d["crs"] = {"type": "name", "properties": {"name": crs}}
    path.write_text(json.dumps(d), encoding="utf-8")


def feat(coords, **props):
    return {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": coords}}


def test_crs_handling_accepts_wgs84_and_rejects_projected(tmp_path):
    ok = tmp_path / "ok.geojson"
    write_geojson(ok, "urn:ogc:def:crs:OGC:1.3:CRS84", [feat(square(70, 30, 71, 31), id="1", n="A")])
    units, crs = load_geojson_units(ok, 2, "id", "n")
    assert units[0]["name"] == "A" and crs.endswith("crs84")
    bad = tmp_path / "bad.geojson"
    write_geojson(bad, "urn:ogc:def:crs:EPSG::32643", [feat(square(70, 30, 71, 31), id="1", n="A")])
    with pytest.raises(ValueError, match="unsupported CRS"):
        load_geojson_units(bad, 2, "id", "n")
    none = tmp_path / "none.geojson"
    write_geojson(none, None, [feat(square(70, 30, 71, 31), id="1", n="A")])
    assert load_geojson_units(none, 2, "id", "n")[1] == "crs84"        # RFC 7946 default


def test_validate_index_accepts_clean_synthetic_data():
    rep = validate_index(synth_index())
    assert rep["valid"], rep["problems"]
    assert rep["level1_count"] == 1 and rep["level2_count"] == 3 and rep["invalid_rings"] == 0


def test_validate_index_flags_bad_geometry_duplicates_and_out_of_country():
    broken_ring = [[[70, 30], [71, 30], [71, 31], [70, 31]]]                        # not closed
    units = [unit(1, "P1", "Punjab", [square(70, 28, 76, 34)]),
             unit(2, "D1", "Dup", [square(72, 30, 73, 31)], "P1"),
             unit(2, "D2", "Dup", [square(73.2, 30, 74, 31)], "P1"),
             unit(2, "D3", "Broken", [broken_ring], "P1"),
             unit(2, "D4", "Far", [square(0, 0, 1, 1)], "P1"),
             unit(2, "D5", "Orphan", [square(75, 30, 76, 31)], "NOPE")]
    rep = validate_index(BoundaryIndex(units, SRC, "crs84"))
    assert not rep["valid"]
    assert rep["level2_duplicate_names"] == ["dup"] and rep["invalid_rings"] >= 1
    assert rep["units_outside_pakistan_extent"] == 1 and rep["districts_with_unknown_parent"] == ["D5"]


def test_validate_index_detects_overlapping_districts():
    units = [unit(1, "P1", "Punjab", [square(70, 28, 76, 34)]),
             unit(2, "A", "A", [square(72, 30, 74, 32)], "P1"), unit(2, "B", "B", [square(72, 30, 74, 32)], "P1")]
    rep = validate_index(BoundaryIndex(units, SRC, "crs84"))
    assert rep["overlap_sample_test"]["failures"] and not rep["valid"]


# ------------------------------------------------------------- crosswalk
def bidx(names):
    units = [unit(1, "P1", "Punjab", [square(70, 28, 76, 34)])]
    for i, (n, parent) in enumerate(names):
        units.append(unit(2, f"D{i}", n, [square(70 + i * 0.1, 30, 70.05 + i * 0.1, 30.05)], parent))
    return BoundaryIndex(units, SRC, "crs84")


def test_crosswalk_exact_alias_declared_alias_and_unmatched_are_deterministic():
    canonical = canon() + [{"id": 11, "name": "Dera Ghazi Khan", "level": 2, "province": "Punjab", "aliases": ["D.G. Khan"]},
                           {"id": 12, "name": "Layyah", "level": 2, "province": "Punjab", "aliases": []}]
    idx = bidx([("Sialkot", "P1"), ("DG Khan", "P1"), ("Leiah", "P1"), ("Atlantis", "P1")])
    rows = build_crosswalk(idx, canonical, {"Leiah": "Layyah"})
    d = {r["boundary_name"]: r for r in rows if r["boundary_level"] == 2}
    assert d["Sialkot"]["match_status"] == "exact" and d["Sialkot"]["pori_admin_unit_id"] == 10
    assert d["DG Khan"]["match_status"] == "alias" and d["DG Khan"]["match_basis"] == "canonical_alias"
    assert d["Leiah"]["match_status"] == "alias" and d["Leiah"]["match_basis"] == "declared_crosswalk_alias" and d["Leiah"]["pori_admin_unit_id"] == 12
    assert d["Atlantis"]["match_status"] == "unmatched" and d["Atlantis"]["pori_admin_unit_id"] is None   # stays visible
    assert rows == build_crosswalk(idx, list(reversed(canonical)), {"Leiah": "Layyah"})                   # deterministic


def test_crosswalk_never_fuzzy_matches():
    rows = build_crosswalk(bidx([("Sialcot", "P1")]), canon(), {})
    assert [r for r in rows if r["boundary_level"] == 2][0]["match_status"] == "unmatched"


def test_crosswalk_ambiguous_when_name_hits_two_canonical_units_or_province_mismatches():
    canonical = canon() + [{"id": 13, "name": "Sialkot", "level": 2, "province": "Sindh", "aliases": []}]
    rows = build_crosswalk(bidx([("Sialkot", "P1")]), canonical, {})
    assert [r for r in rows if r["boundary_level"] == 2][0]["match_status"] == "ambiguous"
    mismatch = build_crosswalk(bidx([("Sialkot", "P1")]), [canon()[0], {**canon()[1], "province": "Sindh"}], {})
    r = [x for x in mismatch if x["boundary_level"] == 2][0]
    assert r["match_status"] == "ambiguous" and "province mismatch" in r["note"] and r["pori_admin_unit_id"] is None


# ------------------------------------------------------------- coordinate -> eligibility policy
POLICY_ALLOW = {"eligible_evidence_statuses": ["authoritative"], "allow_coordinate_derived_eligibility": True}


def coord_ev(status, lat=32.5, lon=74.5, source_type="official"):
    return {"station_name": "Marala", "district": None, "latitude": lat, "longitude": lon, "evidence_status": status,
            "source": "S", "source_type": source_type, "source_record": "R", "evidence_strength": "x"}


def coord_map(entries, policy=POLICY_ALLOW, index=None, canonical=None):
    index = index or synth_index()
    cw = crosswalk_lookup(build_crosswalk(index, canonical or canon(), {}))
    inv = build_inventory([row("Marala")])
    config = {"mapping_version": "t", "mapping_date": "d", "evidence": entries}
    return inv, build_mapping(inv, config, UNITS | {"Sialkot": {"id": 10, "level": 2, "province": "Punjab"}}, CAVEATED, index, cw, policy)


def test_authoritative_coordinates_in_matched_district_are_coordinate_based_and_eligible():
    inv, m = coord_map([coord_ev("authoritative")])
    x = m[0]
    assert x["mapping_status"] == "resolved_coordinate" and x["geography_derivation"] == "coordinate_based"
    assert x["mapping_basis"] == "coordinate_point_in_polygon" and x["eligible_for_admin_risk"] and x["admin_unit_id"] == 10
    assert x["boundary_unit_name"] == "Sialkot" and x["boundary_pcode"] == "D1" and x["boundary_match_basis"] == "point_in_polygon"
    assert x["boundary_source"] == "SYN" and x["boundary_version"] == "v0"
    assert x["mapping_status"] != "resolved_authoritative"                  # never labelled as a source-reported fact
    assert x["evidence"][0]["source"] == "S"                                 # provenance retained


def test_coordinate_eligibility_can_be_disabled_by_policy():
    x = coord_map([coord_ev("authoritative")], policy={**POLICY_ALLOW, "allow_coordinate_derived_eligibility": False})[1][0]
    assert x["mapping_status"] == "resolved_coordinate" and not x["eligible_for_admin_risk"]


def test_secondary_coordinates_are_never_eligible():
    x = coord_map([coord_ev("secondary", source_type="secondary")])[1][0]
    assert x["mapping_status"] == "resolved_inferred" and not x["eligible_for_admin_risk"]


def test_reversed_or_out_of_polygon_coordinates_do_not_map():
    rev = coord_map([coord_ev("authoritative", lat=74.5, lon=32.5)])[1][0]
    assert rev["mapping_status"] == "unresolved" and "likely_reversed" in rev["coordinate_validation"]["flags"] and not rev["eligible_for_admin_risk"]
    out = coord_map([coord_ev("authoritative", lat=33.5, lon=71.0)])[1][0]
    assert out["admin_unit_id"] is None and not out["eligible_for_admin_risk"] and "outside" in out["caveat"]
    edge = coord_map([coord_ev("authoritative", lat=32.5, lon=74.0)])[1][0]
    assert edge["admin_unit_id"] is None and "on_boundary" in edge["caveat"]


def test_coordinate_in_district_without_canonical_match_stays_unresolved_but_keeps_boundary_info():
    x = coord_map([coord_ev("authoritative", lat=30.5, lon=72.5)])[1][0]               # synthetic district "Zeta" has no canonical unit
    assert x["mapping_status"] == "unresolved" and x["admin_unit_id"] is None and not x["eligible_for_admin_risk"]
    assert x["boundary_unit_name"] == "Zeta" and "no canonical match" in x["caveat"]


def test_coordinates_and_district_that_disagree_are_ambiguous():
    e = coord_ev("authoritative")
    d = {"station_name": "Marala", "district": "Jhang", "evidence_status": "authoritative", "source": "S2", "source_type": "official",
         "source_record": "R2", "evidence_strength": "x"}
    x = coord_map([e, d])[1][0]
    assert x["mapping_status"] == "ambiguous" and not x["eligible_for_admin_risk"] and len(x["evidence"]) == 2


def test_official_secondary_is_not_eligible_by_default_and_conflicting_is_ambiguous():
    inv = build_inventory([row("Marala")])
    base = {"station_name": "Marala", "district": "Sialkot", "source": "S", "source_type": "official", "source_record": "R"}
    m = build_mapping(inv, {"mapping_version": "t", "mapping_date": "d", "evidence": [{**base, "evidence_status": "official_secondary"}]},
                      UNITS | {"Sialkot": {"id": 10, "level": 2, "province": "Punjab"}}, CAVEATED)[0]
    assert m["mapping_status"] == "resolved_source_reported" and not m["eligible_for_admin_risk"]
    c = build_mapping(inv, {"mapping_version": "t", "mapping_date": "d", "evidence": [{**base, "evidence_status": "conflicting"}]},
                      UNITS | {"Sialkot": {"id": 10, "level": 2, "province": "Punjab"}}, CAVEATED)[0]
    assert c["mapping_status"] == "ambiguous" and not c["eligible_for_admin_risk"]


def test_caveated_station_stays_ineligible_even_with_authoritative_evidence():
    inv = build_inventory([row("Mangla", "JHELUM")])
    e = {"station_name": "Mangla", "district": "Mangla", "evidence_status": "authoritative", "source": "S", "source_type": "official",
         "source_record": "R"}
    m = build_mapping(inv, {"mapping_version": "t", "mapping_date": "d", "evidence": [e]}, UNITS, CAVEATED, policy=POLICY_ALLOW)[0]
    assert m["mapping_status"] == "caveated" and not m["eligible_for_admin_risk"]


def test_river_and_basin_evidence_never_become_a_district():
    inv = build_inventory([row("Chashma", "INDUS")])
    e = {"station_name": "Chashma", "river": "Indus", "basin": "Indus Basin", "evidence_status": "authoritative", "source": "S",
         "source_type": "official", "source_record": "R"}
    m = build_mapping(inv, {"mapping_version": "t", "mapping_date": "d", "evidence": [e]}, UNITS, CAVEATED, policy=POLICY_ALLOW)[0]
    assert m["admin_unit_id"] is None and m["mapping_status"] == "unresolved" and not m["eligible_for_admin_risk"]


def test_validator_rejects_eligible_mapping_without_authoritative_evidence():
    inv, m = coord_map([coord_ev("secondary", source_type="secondary")])
    m[0]["eligible_for_admin_risk"], m[0]["ineligibility_reason"] = True, None
    assert any("without authoritative evidence" in e for e in validate(inv, m))


def test_risk_engine_consumes_a_coordinate_derived_station_and_labels_it():
    dates = days("2026-05-01", 45)
    rows = [row("Marala", date=d, value=100.0 + i) for i, d in enumerate(dates)]
    inv, m = coord_map([coord_ev("authoritative")])
    mapped = apply_to_gauge_rows(rows, m, inv)
    assert all(r["geography_derivation"] == "coordinate_based" and r["geography_mapping_status"] == "resolved_coordinate" for r in mapped)
    out = run_engine(gold(gauge=mapped), load_config())
    assert {r["admin_unit_id"] for r in out["rows"]} == {10} and out["unresolved"] == []
    inv2, m2 = coord_map([coord_ev("secondary", source_type="secondary")])
    out2 = run_engine(gold(gauge=apply_to_gauge_rows(rows, m2, inv2)), load_config())
    assert out2["rows"] == [] and len(out2["unresolved"]) == 45          # inferred -> preserved unresolved, never consumed


# ------------------------------------------------------------- real boundary dataset
BCFG = load_boundary_cfg()
SRC_CFG = BCFG["sources"][BCFG["active_source"]]
REAL = REPO / SRC_CFG["local_dir"]
needs_real = pytest.mark.skipif(not all((REAL / f).exists() for f in SRC_CFG["files"].values()),
                                reason="HDX boundary files not downloaded in this environment")


def test_boundary_config_documents_provenance_and_policy():
    for k in ("publisher", "dataset", "version", "license", "dataset_url", "resource_url", "crs", "levels", "limitations", "archive_sha256"):
        assert SRC_CFG[k], k
    assert SRC_CFG["government_certified"] is False and "CC BY-IGO" in SRC_CFG["license"]
    assert BCFG["policy"]["eligible_evidence_statuses"] == ["authoritative"]
    assert BCFG["policy"]["secondary_eligible"] is False and BCFG["policy"]["official_secondary_eligible"] is False
    assert BCFG["policy"]["coordinate_derived_label"] == "coordinate_based"


@needs_real
def test_real_boundary_dataset_is_structurally_valid_with_expected_counts():
    rep = validate_index(load_index(BCFG, REPO), BCFG["policy"]["pakistan_bbox"])
    assert rep["valid"], rep["problems"]
    assert rep["level1_count"] == 7 and rep["level2_count"] == 160 and rep["crs_accepted"]
    assert rep["level2_duplicate_names"] == [] and rep["level2_missing_ids"] == 0


@needs_real
def test_real_boundary_known_points_and_outside():
    idx = load_index(BCFG, REPO)
    cw = crosswalk_lookup(build_crosswalk(idx, [{"id": 5, "name": "Lahore", "level": 2, "province": "Punjab", "aliases": []},
                                                {"id": 1, "name": "Punjab", "level": 1, "province": "Punjab", "aliases": []}], {}))
    r = locate_station(idx, cw, 31.5497, 74.3436)                             # Lahore city centre
    assert r["polygon_status"] == "inside" and r["boundary_unit_name"] == "Lahore" and r["pori_admin_unit_id"] == 5
    assert r["geography_derivation"] == "coordinate_based"
    assert locate_station(idx, cw, 0.0, 0.0)["polygon_status"] == "outside"
    assert locate_station(idx, cw, 51.5, -0.1)["polygon_status"] == "outside"


@needs_real
def test_real_crosswalk_keeps_unmatched_units_visible_and_has_no_duplicate_targets():
    idx = load_index(BCFG, REPO)
    cano = [{"id": i + 1, "name": n, "level": 2, "province": p, "aliases": []}
            for i, (n, p) in enumerate([("Lahore", "Punjab"), ("Layyah", "Punjab")])]
    rows = build_crosswalk(idx, cano, BCFG["crosswalk_aliases"])
    assert len(rows) == 7 + 160 and len({(r["boundary_level"], r["boundary_source_id"]) for r in rows}) == len(rows)
    st = {r["boundary_name"]: r["match_status"] for r in rows if r["boundary_level"] == 2}
    assert st["Lahore"] == "exact" and st["Leiah"] == "alias" and st["Bagh"] == "unmatched"
    targets = [r["pori_admin_unit_id"] for r in rows if r["pori_admin_unit_id"] and r["boundary_level"] == 2]
    assert len(targets) == len(set(targets))


# ------------------------------------------------------------- station matching (no fuzzy)
def test_evidence_matches_stations_by_conservative_normalized_name_only():
    inv = build_inventory([row("G.S. Wala", "SUTLEJ"), row("Lai FD and DEO", "NULLAHS"), row("Lai", "NULLAHS")])
    e = {"district": "Sialkot", "evidence_status": "authoritative", "source": "S", "source_type": "official", "source_record": "R"}
    config = {"mapping_version": "t", "mapping_date": "d", "evidence": [{"station_name": "G.S.Wala", **e}, {"station_name": "Lai", **e}]}
    by = {m["station_name"]: m for m in build_mapping(inv, config, UNITS | {"Sialkot": {"id": 10, "level": 2, "province": "Punjab"}}, CAVEATED)}
    assert by["G.S. Wala"]["admin_unit_id"] == 10          # punctuation/spacing variant of the same name
    assert by["Lai"]["admin_unit_id"] == 10
    assert by["Lai FD and DEO"]["admin_unit_id"] is None   # a longer, different name is never matched fuzzily


def test_station_without_any_evidence_gets_no_fabricated_geography():
    inv = build_inventory([row("Kalabagh", "INDUS")])
    m = build_mapping(inv, {"mapping_version": "t", "mapping_date": "d", "evidence": []}, UNITS, CAVEATED)[0]
    assert m["admin_unit_id"] is None and m["evidence"] == [] and m["coordinate_validation"] is None and m["boundary_pcode"] is None
