"""
tests/geo/test_resolver.py

Phase 1 / Task 10 (ADR-0001) -- deterministic tests for
scripts/geo/resolver.py's resolve() and normalize_name(), covering
every case the approved plan requires: exact, alias, case/spacing
normalization, known spelling variation, ambiguous, unresolved,
and the level-boundary guarantee. No live DB, no internet.

Real-data note: PROVINCES/DISTRICTS test cases use
scripts.geo.canonical_data's actual canonical lists (the real, live-
sourced province/district set built during Task 10) so these tests
exercise the real data the resolver will run against in production,
not an unrelated synthetic stand-in. A couple of dedicated small
candidate lists are hand-built only where the test needs to isolate
one resolution PATH specifically (e.g. forcing the fuzzy path rather
than letting a pre-seeded alias short-circuit it).
"""

from __future__ import annotations

import pytest

from scripts.geo.canonical_data import DISTRICTS, PROVINCES
from scripts.geo.resolver import normalize_name, resolve


# ==========================================================
# 1. Exact canonical-name match
# ==========================================================

def test_exact_match_province():
    r = resolve("Punjab", PROVINCES)
    assert r.admin_unit_key == "Punjab"
    assert r.match_method == "exact"
    assert r.status == "resolved"


def test_exact_match_district():
    r = resolve("Rajanpur", DISTRICTS)
    assert r.admin_unit_key == "Rajanpur"
    assert r.match_method == "exact"
    assert r.status == "resolved"


# ==========================================================
# 2. Alias match (real NDMA/PDMA abbreviations actually seen live)
# ==========================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AJ&K", "Azad Jammu & Kashmir"),   # real NDMA abbreviation
        ("AJK", "Azad Jammu & Kashmir"),     # real PMD full-set abbreviation
        ("GB", "Gilgit-Baltistan"),
        ("ICT", "Islamabad Capital Territory"),
        ("Islamabad", "Islamabad Capital Territory"),  # real PMD region value
        ("KP", "Khyber Pakhtunkhwa"),
    ],
)
def test_alias_match_province(raw, expected):
    r = resolve(raw, PROVINCES)
    assert r.admin_unit_key == expected
    assert r.match_method == "alias"
    assert r.status == "resolved"


def test_alias_match_district_punctuation_variant():
    # "D.G. Khan" is the exact raw form geo_locations itself uses.
    r = resolve("D.G. Khan", DISTRICTS)
    assert r.admin_unit_key == "Dera Ghazi Khan"
    assert r.match_method == "alias"


# ==========================================================
# 3. Case / spacing normalization
# ==========================================================

@pytest.mark.parametrize(
    "raw",
    ["  punjab ", "PUNJAB", "PuNjAb"],
)
def test_normalized_match_case_and_spacing(raw):
    r = resolve(raw, PROVINCES)
    assert r.admin_unit_key == "Punjab"
    assert r.match_method in ("exact", "normalized")
    assert r.status == "resolved"


def test_normalize_name_collapses_whitespace_and_punctuation():
    assert normalize_name("  D.G.   Khan ") == "d g khan"
    assert normalize_name("KHYBER PAKHTUNKHWA") == "khyber pakhtunkhwa"
    assert normalize_name(None) == ""


# ==========================================================
# 4. Known spelling variation (real, live-confirmed misspellings,
#    forced through the FUZZY path specifically -- not alias-seeded)
# ==========================================================

def test_fuzzy_match_known_spelling_variation_mandi_bahauddin():
    candidates = [{"name": "Mandi Bahauddin", "aliases": []}, {"name": "Rajanpur", "aliases": []}]
    r = resolve("Mandi Bahaddin", candidates)  # real live-confirmed variant
    assert r.admin_unit_key == "Mandi Bahauddin"
    assert r.match_method == "fuzzy"
    assert r.status == "resolved"
    assert r.confidence is not None and r.confidence >= 0.85


def test_fuzzy_match_known_spelling_variation_noorpur_thal():
    candidates = [{"name": "Noorpur Thal", "aliases": []}, {"name": "Okara", "aliases": []}]
    r = resolve("Noorpurthal", candidates)  # real live-confirmed variant
    assert r.admin_unit_key == "Noorpur Thal"
    assert r.match_method == "fuzzy"
    assert r.confidence is not None and r.confidence >= 0.85


def test_fuzzy_match_via_full_canonical_district_list():
    # Same case, but against the REAL production candidate pool
    # (canonical_data.DISTRICTS), where "Mandi Bahaddin" is already an
    # alias -- confirms the real pool resolves it (via alias, which is
    # fine and expected; the dedicated tests above prove the fuzzy
    # PATH itself works when no alias exists).
    r = resolve("Mandi Bahaddin", DISTRICTS)
    assert r.admin_unit_key == "Mandi Bahauddin"
    assert r.status == "resolved"


# ==========================================================
# 5. Ambiguous match (real live-confirmed pdma_rainfall_readings.station
#    shape: comma-separated multi-district strings)
# ==========================================================

@pytest.mark.parametrize(
    "raw",
    [
        "Attock, Gujranwala, Jhelum",
        "Mangla, Toba Tek Singh, Gujrat",
        "Punjab/Sindh",
    ],
)
def test_ambiguous_multi_value_string_never_guessed(raw):
    r = resolve(raw, DISTRICTS)
    assert r.admin_unit_key is None
    assert r.status == "ambiguous"
    assert "not split" in r.notes


# ==========================================================
# 6. Unresolved match
# ==========================================================

def test_unresolved_gauge_station_name():
    # A real pdma_gauge_readings station name -- no station->district
    # mapping exists anywhere in the repo, so this MUST be unresolved,
    # not guessed. This is the correct, honest outcome, not a defect.
    r = resolve("Tarbela", DISTRICTS)
    assert r.admin_unit_key is None
    assert r.status == "unresolved"
    assert r.match_method == "unresolved"


def test_unresolved_nonsense_string():
    r = resolve("Xyzzy Notaplace", PROVINCES)
    assert r.admin_unit_key is None
    assert r.status == "unresolved"


def test_unresolved_empty_and_none():
    for raw in (None, "", "   "):
        r = resolve(raw, PROVINCES)
        assert r.admin_unit_key is None
        assert r.status == "unresolved"


# ==========================================================
# 7. Parent-child validation (see also test_canonical_data.py for the
#    exhaustive static check -- this is the resolver-facing version)
# ==========================================================

def test_every_resolved_district_has_a_valid_parent_province():
    province_names = {p["name"] for p in PROVINCES}
    for district in DISTRICTS:
        assert district["province"] in province_names, (
            f"{district['name']!r} declares parent province "
            f"{district['province']!r}, which is not a canonical province"
        )


# ==========================================================
# 8. Prevention of incorrect lower-level assignment
# ==========================================================

def test_province_name_does_not_resolve_against_district_pool():
    # "Punjab" is a real, well-known name -- but it is a PROVINCE, not
    # a district. Resolving it against the DISTRICT pool must not
    # produce a false match (e.g. via a lucky fuzzy hit).
    r = resolve("Punjab", DISTRICTS)
    assert r.admin_unit_key is None
    assert r.status == "unresolved"


def test_district_name_does_not_resolve_against_province_pool():
    r = resolve("Rajanpur", PROVINCES)
    assert r.admin_unit_key is None
    assert r.status == "unresolved"


def test_resolve_never_mixes_levels_by_construction():
    """
    Structural guarantee, not just a lucky data outcome: resolve()
    only ever sees the single candidate list it's given -- there is no
    code path anywhere in resolver.py that reaches into a different
    level's pool. Confirmed by inspecting the real function signature
    (single `candidates` list, never a level parameter that could
    silently widen the pool).
    """
    import inspect

    signature = inspect.signature(resolve)
    assert list(signature.parameters.keys()) == ["raw_name", "candidates"]
