"""
tests/geo/test_canonical_data.py

Phase 1 / Task 10 (ADR-0001) -- static structural tests for
scripts/geo/canonical_data.py. No database, no I/O -- these validate
the data structure itself (the pure Python lists), not any live query.
"""

from __future__ import annotations

from scripts.geo.canonical_data import DISTRICTS, PROVINCES


def test_seven_canonical_provinces():
    # Exactly the 7 real Pakistani provinces/territories/regions --
    # not more, not fewer, and no duplicates.
    names = [p["name"] for p in PROVINCES]
    assert len(names) == 7
    assert len(names) == len(set(names))


def test_every_province_has_required_fields():
    for p in PROVINCES:
        assert isinstance(p["name"], str) and p["name"].strip()
        assert isinstance(p["aliases"], list)
        assert isinstance(p["source"], str) and p["source"].strip()


def test_no_duplicate_district_names():
    names = [d["name"] for d in DISTRICTS]
    assert len(names) == len(set(names)), "canonical district list must not contain duplicate names"


def test_every_district_has_a_valid_parent_province():
    province_names = {p["name"] for p in PROVINCES}
    for d in DISTRICTS:
        assert d["province"] in province_names, (
            f"district {d['name']!r} has parent province {d['province']!r}, "
            f"which is not in the canonical province list"
        )


def test_every_district_has_required_fields():
    for d in DISTRICTS:
        assert isinstance(d["name"], str) and d["name"].strip()
        assert isinstance(d["province"], str) and d["province"].strip()
        assert isinstance(d["aliases"], list)
        assert isinstance(d["lat"], float)
        assert isinstance(d["lon"], float)
        assert isinstance(d["source"], str) and d["source"].strip()


def test_no_alias_collides_with_a_different_canonical_district_name():
    """
    No district's alias string may be identical to a DIFFERENT
    district's canonical name -- that would make resolution genuinely
    ambiguous by construction, silently. (An alias equal to its OWN
    district's name is redundant but harmless -- not tested against.)
    """
    canonical_names = {d["name"] for d in DISTRICTS}
    for d in DISTRICTS:
        for alias in d["aliases"]:
            other_names = canonical_names - {d["name"]}
            assert alias not in other_names, (
                f"alias {alias!r} on district {d['name']!r} collides with "
                f"another district's canonical name"
            )


def test_caveat_entries_are_documented_not_silently_included():
    """
    The four known-inaccurate entries inherited from geo_locations
    (Mangla, Fort Munro, Kamra, Joharabad -- see canonical_data.py's
    module docstring) must each carry an explicit `caveat` field, so
    their limitation is queryable/visible, not silently indistinguishable
    from a real district.
    """
    expected_caveat_names = {"Mangla", "Fort Munro", "Kamra", "Joharabad"}
    flagged = {d["name"] for d in DISTRICTS if "caveat" in d}
    assert expected_caveat_names <= flagged


def test_real_district_count_matches_documented_union():
    """
    69 = 40 Punjab (geo_locations) + 3 AJK + 10 Sindh + 1 ICT + 8 KP +
    5 Balochistan + 2 GB (all district_master_csv-sourced except the
    Punjab block and 2 of the 3 AJK entries) -- see canonical_data.py's
    module docstring and docs/geo/GEOGRAPHIC_FOUNDATION.md for the
    full reconciliation. This test pins the real, computed number so a
    future silent change is caught, not the other way around.
    """
    assert len(DISTRICTS) == 69
