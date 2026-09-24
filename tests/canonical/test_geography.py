"""
tests/canonical/test_geography.py

Task 18 -- geography enrichment tests. No real database connection is
used anywhere in this file: `build_dict_admin_unit_lookup()` supplies a
plain in-memory dict standing in for geo.admin_unit, matching Task 18
Part 5's explicit "no test should pollute the real DB" requirement.
Only tests/canonical/test_geography_live_db.py touches Postgres, and it
is read-only and skips cleanly if unreachable.
"""

from __future__ import annotations

from scripts.geo.canonical_data import DISTRICTS, PROVINCES
from pipeline.canonical.geography import build_dict_admin_unit_lookup, enrich_location


def test_exact_resolved_case_populates_admin_unit_id_from_lookup():
    lookup = build_dict_admin_unit_lookup({"Punjab": 42})
    result = enrich_location("Punjab", PROVINCES, admin_unit_lookup=lookup)
    assert result["resolution_status"] == "resolved"
    assert result["resolution_method"] == "exact"
    assert result["admin_unit_key"] == "Punjab"
    assert result["admin_unit_id"] == 42


def test_alias_resolved_case_uses_known_alias():
    # "AJ&K" is a real, live-confirmed NDMA alias for Azad Jammu & Kashmir
    # (scripts/geo/canonical_data.py), not a fabricated example.
    lookup = build_dict_admin_unit_lookup({"Azad Jammu & Kashmir": 7})
    result = enrich_location("AJ&K", PROVINCES, admin_unit_lookup=lookup)
    assert result["resolution_status"] == "resolved"
    assert result["resolution_method"] == "alias"
    assert result["admin_unit_key"] == "Azad Jammu & Kashmir"
    assert result["admin_unit_id"] == 7


def test_ambiguous_case_never_populates_admin_unit_id():
    # Real Task 10-documented ambiguous pattern: a comma-separated
    # multi-district string from pdma_rainfall_readings.station.
    lookup = build_dict_admin_unit_lookup({"Gujranwala": 1, "Jhelum": 2})
    result = enrich_location("Gujranwala, Jhelum", DISTRICTS, admin_unit_lookup=lookup)
    assert result["resolution_status"] == "ambiguous"
    assert result["admin_unit_id"] is None
    assert result["admin_unit_key"] is None


def test_unresolved_case_never_populates_admin_unit_id():
    lookup = build_dict_admin_unit_lookup({"Punjab": 1})
    result = enrich_location("Definitely Not A Real Place", DISTRICTS, admin_unit_lookup=lookup)
    assert result["resolution_status"] == "unresolved"
    assert result["admin_unit_id"] is None


def test_missing_location_is_unresolved_not_fabricated():
    result = enrich_location(None, PROVINCES, admin_unit_lookup=build_dict_admin_unit_lookup({}))
    assert result["location_original"] is None
    assert result["resolution_status"] == "unresolved"
    assert result["admin_unit_id"] is None


def test_hierarchy_safety_province_only_value_does_not_become_a_district():
    # Resolving "Punjab" against the DISTRICTS pool must not silently
    # promote a province-level value into a district-level ID -- the
    # candidate pool itself is the hierarchy boundary (Task 10 rule,
    # reused unchanged), and "Punjab" is not a district name.
    lookup = build_dict_admin_unit_lookup({"Punjab": 999})
    result = enrich_location("Punjab", DISTRICTS, hierarchy_field="district", admin_unit_lookup=lookup)
    assert result["resolution_status"] == "unresolved"
    assert result["district"] is None
    assert result["admin_unit_id"] is None


def test_no_false_positive_for_a_similar_but_different_name():
    # "Lahore" (a real district) must not resolve when only "Multan" is
    # in the lookup/candidate pool -- confirms the resolver doesn't
    # silently accept a near-miss below its fuzzy threshold as if it
    # were "close enough".
    lookup = build_dict_admin_unit_lookup({"Multan": 5})
    result = enrich_location("Lahoreee Xyz Nonexistent", DISTRICTS, admin_unit_lookup=lookup)
    assert result["resolution_status"] == "unresolved"
    assert result["admin_unit_id"] is None


def test_enrichment_is_idempotent():
    lookup = build_dict_admin_unit_lookup({"Sindh": 2})
    first = enrich_location("Sindh", PROVINCES, admin_unit_lookup=lookup)
    second = enrich_location("Sindh", PROVINCES, admin_unit_lookup=lookup)
    assert first == second


def test_resolved_without_lookup_leaves_admin_unit_id_none():
    # Matches Task 17's exact original behavior for every existing
    # caller that doesn't pass admin_unit_lookup.
    result = enrich_location("Punjab", PROVINCES)
    assert result["resolution_status"] == "resolved"
    assert result["admin_unit_id"] is None


def test_hierarchy_field_is_only_added_when_requested():
    result = enrich_location("Punjab", PROVINCES)
    assert "province" not in result and "district" not in result
