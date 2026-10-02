from pipeline.geo.gauge_mapping import apply_to_gauge_rows, build_mapping
from pipeline.geo.gauge_station import build_inventory
from pipeline.geo.hydrography import hydrographic_context, has_river_context
from tests.geo.test_gauge_station_mapping import CAVEATED, UNITS, cfg, row


def test_main_river_is_source_reported_not_authoritative_and_has_no_basin():
    h = hydrographic_context("CHENAB")
    assert h["river_name"] == "Chenab" and h["river_context_status"] == "source_reported"
    assert h["basin_name"] is None and h["catchment_name"] is None and h["basin_context_status"] == "unresolved"


def test_hill_torrent_group_is_not_treated_as_a_river():
    h = hydrographic_context("DG KHAN HILL TORRENTS")
    assert h["river_heading_kind"] == "torrent_or_nullah_group" and not has_river_context(h)


def test_corrupt_heading_is_unresolved_not_used():
    h = hydrographic_context("NULLAHS DATA SOURCE: F")
    assert h["river_name"] is None and h["hydrographic_context_status"] == "unresolved" and "artefact" in h["hydrographic_note"]
    assert hydrographic_context(None)["river_context_status"] == "unresolved"


def test_river_never_becomes_a_district_and_basin_never_an_admin_unit():
    rows = [row("Chashma", "INDUS"), row("Taunsa", "INDUS")]
    inv = build_inventory(rows)
    m = build_mapping(inv, cfg({}), UNITS, CAVEATED)
    mapped = apply_to_gauge_rows(rows, m, inv)
    assert all(s["river_name"] == "Indus" for s in inv)              # hydrographic context kept
    assert all(x["admin_unit_id"] is None and x["admin_unit_name"] is None for x in m)   # but no district
    assert all(r["admin_unit_id"] is None for r in mapped)
    assert all(s["basin_name"] is None for s in inv)


def test_gauge_with_null_admin_unit_still_carries_river_context_and_mapping_fields():
    inv = build_inventory([row("Kalabagh", "INDUS")])
    m = build_mapping(inv, cfg({}), UNITS, CAVEATED)[0]
    assert m["admin_unit_id"] is None
    for k in ("mapping_status", "mapping_basis", "mapping_source", "mapping_confidence", "caveat", "mapping_version"):
        assert k in m
    assert inv[0]["river_name"] == "Indus"
