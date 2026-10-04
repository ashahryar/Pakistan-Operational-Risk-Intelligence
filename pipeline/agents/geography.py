"""Task 34 -- geography resolution for the agent: an adapter over the EXISTING deterministic resolver (pipeline/intelligence/context.py ->
scripts/geo/resolver.normalize_name + the canonical names/aliases). Exact / alias / normalised matches only; NEVER fuzzy. No new mapping is added and nothing is
inferred: a river, gauge, tehsil or town that is not a canonical name or alias stays unresolved, and an ambiguous name (for example "Islamabad", which is both a
province-level alias and a district) is returned with its candidate interpretations instead of being guessed.
Pure: the caller supplies the admin-unit rows (id, level, name, province) read from geo.admin_unit.
"""

from __future__ import annotations

from pipeline.agents.router import unrecognized_places
from pipeline.intelligence.context import extract_context


def resolve_place(text: str, units: list[dict]) -> dict:
    q = extract_context(text, units)
    candidates = []
    if q.geography_status in ("ambiguous", "multiple"):
        for m in q.mentions:
            if m["status"] in ("ambiguous", "resolved"):
                candidates += [{**c, "mention": m["raw"]} for c in m["candidates"]]
    return {"status": q.geography_status, "unit": q.admin_unit, "province": q.province, "mentions": q.mentions, "candidates": candidates, "notes": q.notes,
            "unrecognized_places": unrecognized_places(text, q.mentions)}
