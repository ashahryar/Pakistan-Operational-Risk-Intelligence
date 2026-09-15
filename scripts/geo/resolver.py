"""
scripts/geo/resolver.py

Phase 1 / Task 10 (ADR-0001) -- pure name-resolution logic for the
geographic foundation. No database import, no file I/O, no import-time
side effect -- directly unit-tested by tests/geo/test_resolver.py with
small in-memory candidate lists.

Resolution order (first match wins), matching the approved plan:
  1. exact       -- raw_name (whitespace-stripped) equals a candidate's
                     canonical name exactly.
  2. alias        -- raw_name matches a known alias string.
  3. normalized   -- after lowercasing + whitespace/punctuation
                     normalization, matches a canonical name or alias.
  4. fuzzy        -- stdlib difflib.SequenceMatcher ratio against every
                     candidate's normalized name; accepted only if the
                     best ratio clears FUZZY_THRESHOLD and is not tied
                     with a second-best candidate within FUZZY_TIE_GAP.
  5. ambiguous    -- raw_name contains a structural multi-value
                     separator (comma or slash) -- never split or
                     guessed.
  6. unresolved   -- nothing above matched.

A candidate is a dict with at least {"name": str} and optionally
{"aliases": [str, ...]}. Callers pass ONLY the candidate pool
appropriate to what's being resolved (e.g. provinces-only or
districts-only) -- resolve() never mixes levels, so it structurally
cannot return a district match for a province-level lookup or vice
versa (CLAUDE.md rule 7 / the plan's "never infer a lower geographic
level" requirement).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

FUZZY_THRESHOLD = 0.85
FUZZY_TIE_GAP = 0.03

_STRUCTURAL_SEPARATORS = re.compile(r"[,/]")
_PUNCT_RE = re.compile(r"[.\-_]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """
    Lowercases, strips leading/trailing whitespace, collapses internal
    whitespace, and removes common punctuation (`.`, `-`, `_`) that
    varies harmlessly between sources (e.g. "D.G. Khan" / "D-G-Khan").
    Does NOT remove commas/slashes -- those are structural-ambiguity
    signals handled separately by resolve(), not noise to strip.
    """
    if raw is None:
        return ""
    value = _PUNCT_RE.sub(" ", raw)
    value = _WHITESPACE_RE.sub(" ", value)
    return value.strip().lower()


@dataclass
class Resolution:
    admin_unit_key: str | None
    match_method: str  # 'exact' | 'alias' | 'normalized' | 'fuzzy' | 'unresolved'
    confidence: float | None
    status: str  # 'resolved' | 'ambiguous' | 'unresolved'
    notes: str = ""


def resolve(raw_name: str, candidates: list[dict]) -> Resolution:
    """
    Resolves `raw_name` against `candidates` (a list of
    {"name": str, "aliases": [str, ...]} dicts -- ONE geographic level
    only, e.g. provinces-only or districts-only). Returns a Resolution
    describing what matched (if anything) and how.
    """
    if raw_name is None or not raw_name.strip():
        return Resolution(None, "unresolved", None, "unresolved", "empty/null raw_name")

    stripped = raw_name.strip()

    # Structural ambiguity: a raw value naming more than one place
    # (e.g. "Attock, Gujranwala, Jhelum") is never split or guessed.
    if _STRUCTURAL_SEPARATORS.search(stripped):
        return Resolution(
            None, "unresolved", None, "ambiguous",
            "comma/slash-separated multi-value string, not split",
        )

    # 1. Exact
    for c in candidates:
        if stripped == c["name"]:
            return Resolution(c["name"], "exact", None, "resolved")

    # 2. Alias
    for c in candidates:
        for alias in c.get("aliases", []):
            if stripped == alias:
                return Resolution(c["name"], "alias", None, "resolved")

    # 3. Normalized
    normalized_raw = normalize_name(stripped)
    for c in candidates:
        if normalized_raw == normalize_name(c["name"]):
            return Resolution(c["name"], "normalized", None, "resolved")
        for alias in c.get("aliases", []):
            if normalized_raw == normalize_name(alias):
                return Resolution(c["name"], "normalized", None, "resolved")

    # 4. Fuzzy (stdlib difflib only -- no fuzzy-matching library is
    # installed anywhere in this repo, confirmed during Task 10
    # planning, and none is added for this MVP).
    scored = []
    for c in candidates:
        names_to_check = [c["name"], *c.get("aliases", [])]
        best_for_candidate = max(
            difflib.SequenceMatcher(None, normalized_raw, normalize_name(n)).ratio()
            for n in names_to_check
        )
        scored.append((best_for_candidate, c["name"]))
    scored.sort(reverse=True)

    if scored:
        best_ratio, best_name = scored[0]
        second_ratio = scored[1][0] if len(scored) > 1 else 0.0
        if best_ratio >= FUZZY_THRESHOLD and (best_ratio - second_ratio) > FUZZY_TIE_GAP:
            return Resolution(best_name, "fuzzy", round(best_ratio, 3), "resolved")
        if best_ratio >= FUZZY_THRESHOLD:
            return Resolution(
                None, "unresolved", round(best_ratio, 3), "ambiguous",
                f"fuzzy tie between top candidates near '{best_name}' (ratio={best_ratio:.3f})",
            )

    # 6. Unresolved -- report the best (rejected) fuzzy candidate for
    # future manual review, even though it wasn't accepted.
    best_hint = ""
    if scored:
        best_ratio, best_name = scored[0]
        best_hint = f"closest candidate was '{best_name}' (ratio={best_ratio:.3f}, below threshold)"
    return Resolution(None, "unresolved", None, "unresolved", best_hint)
