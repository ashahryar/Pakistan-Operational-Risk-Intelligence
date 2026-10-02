"""Station inventory built from the ACTUAL Gold gauge rows. One record per distinct station.

Only source-supported fields are populated: the PDMA gauge feed carries no coordinates, no
station ids, no basin and no district, so those fields are null -- never invented.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

SOURCE = "pdma"


def normalize_station_name(name: Any) -> str:
    """Lowercase, punctuation -> space, collapsed whitespace (display/search form)."""
    s = re.sub(r"[^0-9a-z]+", " ", str(name or "").lower().replace(".", ""))
    return re.sub(r"\s+", " ", s).strip()


def match_key(name: Any) -> str:
    """Compact comparison form: 'G.S. Wala' == 'G.S.Wala' == 'gs wala'."""
    return normalize_station_name(name).replace(" ", "")


def _river_key(river: Any) -> str:
    return match_key(river)


def build_inventory(gauge_rows: list[dict]) -> list[dict]:
    """-> deterministic list of station records (sorted by station_key)."""
    from pipeline.geo.hydrography import hydrographic_context

    by_name: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in gauge_rows:
        name = r.get("station_name") or r.get("location_original")
        if not match_key(name):
            continue
        by_name[match_key(name)][_river_key(r.get("river_name"))].append(r)

    out = []
    for mk, by_river in by_name.items():
        # same name under >1 distinct river => genuinely separate stations; never merged.
        split = len(by_river) > 1
        for rk, rows in by_river.items():
            variants = sorted({str(r.get("station_name") or r.get("location_original")) for r in rows})
            rivers = sorted({str(r["river_name"]) for r in rows if r.get("river_name")})
            dates = sorted({r["date"] for r in rows if r.get("date")})
            gold_units = sorted({r["admin_unit_id"] for r in rows if r.get("admin_unit_id") and r.get("resolution_status") == "resolved"})
            hydro = hydrographic_context(rivers[0] if rivers else None)
            out.append({
                "station_key": f"{SOURCE}:{mk}" + (f":{rk}" if split else ""),
                "station_name": variants[0],
                "normalized_station_name": normalize_station_name(variants[0]),
                "match_key": mk,
                "source": SOURCE,
                "source_station_id": None,        # the feed publishes none
                "source_name_variants": variants,
                "latitude": None, "longitude": None,   # not in the source; never fabricated
                "river_name_reported": rivers[0] if rivers else None,
                **hydro,
                "observation_count": len(rows),
                "date_min": dates[0] if dates else None, "date_max": dates[-1] if dates else None,
                "legacy_gold_admin_unit_ids": gold_units,
                "source_record_example": ((rows[0].get("provenance") or {}).get("sources") or [{}])[0].get("source_record_id"),
            })
    out.sort(key=lambda s: s["station_key"])
    keys = [s["station_key"] for s in out]
    assert len(keys) == len(set(keys)), "station_key must be unique"
    return out
