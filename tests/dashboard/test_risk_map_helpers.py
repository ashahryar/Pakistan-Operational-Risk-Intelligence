"""Task 27 -- pure map/data transformation helpers (no Streamlit, no HTTP, no database)."""

import pandas as pd

from dashboard.utils.risk_map_helpers import (
    NO_DATA,
    SCORE_UNAVAILABLE,
    STATUS_COLORS,
    STATUS_ORDER,
    dates_from_rows,
    feature_rows,
    filter_rows,
    is_feature_collection,
    map_frame,
    mapped_geojson,
    merge_risk_into_features,
    risk_score_text,
    signal_summary,
    summarize,
    unmapped_risk_frame,
)

SQUARE = {"type": "Polygon", "coordinates": [[[70, 30], [71, 30], [71, 31], [70, 31], [70, 30]]]}


def feat(uid, name, status, geom=SQUARE, score=None, **extra):
    props = {"admin_unit_id": uid, "admin_unit_name": name, "admin_level": 2, "province": "Punjab", "risk_status": status,
             "risk_score": score, "risk_confidence": "MEDIUM" if status else None, "risk_basis": "THRESHOLD_BASED" if status else None,
             "risk_date": "2026-09-16" if status else None, "top_risk_domain": None, "data_coverage_pct": 33.33 if status else None,
             "calculation_version": "risk-engine-1.0.0" if status else None}
    props.update(extra)
    return {"type": "Feature", "id": uid, "geometry": geom, "properties": props}


def fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def sample():
    return fc(feat(1, "Lahore", "HIGH"), feat(2, "Multan", "CRITICAL"), feat(3, "Attock", "INSUFFICIENT_DATA"),
              feat(4, "Jhelum", "LOW"), feat(5, "Okara", "MODERATE"), feat(6, "Boundary only", None),
              feat(7, "Mangla", "INSUFFICIENT_DATA", geom=None))


def test_valid_feature_collection_detection():
    assert is_feature_collection(sample())
    assert not is_feature_collection({"type": "Feature"}) and not is_feature_collection(None) and not is_feature_collection([])
    assert feature_rows(None).empty and list(feature_rows(None).columns)[0] == "admin_unit_id"


def test_all_current_risk_statuses_are_known_and_coloured():
    for s in ("INSUFFICIENT_DATA", "LOW", "MODERATE", "HIGH", "CRITICAL"):
        assert s in STATUS_ORDER and s in STATUS_COLORS
    assert NO_DATA in STATUS_COLORS and NO_DATA not in STATUS_ORDER      # a display category, not a risk status


def test_null_geometry_is_preserved_not_dropped_or_drawn():
    c = sample()
    assert len(c["features"]) == 7 and len(mapped_geojson(c)["features"]) == 6
    assert "Mangla" not in set(map_frame(c)["admin_unit_name"])
    assert feature_rows(c).set_index("admin_unit_name").loc["Mangla", "has_geometry"] is False or not feature_rows(c).set_index("admin_unit_name").loc["Mangla", "has_geometry"]


def test_areas_with_boundary_but_no_risk_are_a_separate_category():
    f = map_frame(sample())
    assert f.set_index("admin_unit_name").loc["Boundary only", "status"] == NO_DATA
    assert f.set_index("admin_unit_name").loc["Lahore", "status"] == "HIGH"


def test_null_risk_score_stays_null_and_is_displayed_as_unavailable():
    f = feature_rows(sample())
    assert f["risk_score"].isna().all()
    assert risk_score_text(None) == SCORE_UNAVAILABLE and "null" in SCORE_UNAVAILABLE
    assert risk_score_text(2.5) == "2.5"                                  # a real value would be shown as-is, never invented


def test_missing_properties_become_none_not_defaults():
    odd = fc({"type": "Feature", "id": 9, "geometry": SQUARE, "properties": {"admin_unit_name": "X"}},
             {"type": "Feature", "id": 10, "geometry": SQUARE, "properties": None})
    f = feature_rows(odd)
    assert list(f["admin_unit_id"]) == [9, 10] and f["risk_status"].isna().all() and f["risk_score"].isna().all()
    assert set(map_frame(odd)["status"]) == {NO_DATA}


def test_unmatched_boundary_units_never_appear_as_risk_areas():
    # an unmatched boundary has no canonical unit, so the API never returns it; if a feature has no risk and no geometry
    # it is simply absent from the unmapped-risk list
    c = fc(feat(1, "A", "LOW"), feat(2, "Unmatched", None, geom=None))
    assert unmapped_risk_frame(c).empty
    assert len(unmapped_risk_frame(sample())) == 1 and unmapped_risk_frame(sample()).iloc[0]["admin_unit_name"] == "Mangla"


def test_summary_counts_use_the_apis_statuses():
    s = summarize(sample())
    assert s["total_areas"] == 7 and s["areas_with_risk"] == 6 and s["areas_without_geometry"] == 1
    assert (s["high"], s["critical"], s["insufficient_data"]) == (1, 1, 2) and s["risk_records_without_boundary"] == 1
    assert s["by_status"] == {"CRITICAL": 1, "HIGH": 1, "MODERATE": 1, "LOW": 1, "INSUFFICIENT_DATA": 2}


def test_summary_of_an_empty_scope():
    s = summarize(fc())
    assert s["total_areas"] == 0 and s["high"] == 0 and s["by_status"] == {}


def test_merging_a_chosen_date_replaces_risk_and_keeps_geometry():
    rows = [{"admin_unit_id": 1, "risk_status": "CRITICAL", "risk_score": None, "risk_date": "2026-09-01", "risk_confidence": "LOW",
             "risk_basis": "ALERT_DRIVEN", "top_risk_domain": "hazard_alert", "data_coverage_pct": 50.0, "calculation_version": "v"},
            {"admin_unit_id": 99, "risk_status": "LOW", "admin_unit_name": "No boundary", "province": "Sindh", "risk_date": "2026-09-01"}]
    c = sample()
    merged = merge_risk_into_features(c, rows)
    by = feature_rows(merged).set_index("admin_unit_id")
    assert by.loc[1, "risk_status"] == "CRITICAL" and by.loc[1, "risk_date"] == "2026-09-01"
    assert pd.isna(by.loc[2, "risk_status"]) and merged["features"][1]["geometry"] == SQUARE      # no row that day -> no data
    assert c["features"][0]["properties"]["risk_status"] == "HIGH"                                 # input not mutated
    s = summarize(c, rows)
    assert s["areas_with_risk"] == 1 and s["critical"] == 1 and s["high"] == 0
    um = unmapped_risk_frame(c, rows)
    assert list(um["admin_unit_id"]) == [99]                                                       # risk without a drawn boundary is listed


def test_signal_summary_keeps_unobserved_signals_as_not_observed_not_zero():
    t = signal_summary({"rainfall": 0.0, "gauge": None, "air_quality": 0.4})
    d = dict(zip(t["signal"], t["value"]))
    assert d["rainfall"] == 0.0 and d["gauge"] == "not observed" and d["air quality"] == 0.4
    assert signal_summary(None).empty


def test_dates_and_level_filter_helpers():
    rows = [{"risk_date": "2026-09-01", "admin_level": 1}, {"risk_date": "2026-09-16", "admin_level": 2}, {"risk_date": "2026-09-16", "admin_level": 2}, {"admin_level": 2}]
    assert dates_from_rows(rows) == ["2026-09-16", "2026-09-01"]
    assert len(filter_rows(rows, 2)) == 3 and len(filter_rows(rows, None)) == 4
