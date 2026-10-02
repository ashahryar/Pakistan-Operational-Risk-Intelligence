"""Hydrographic context -- kept strictly separate from administrative geography.

A river or hill-torrent group is NOT a district and a basin is NOT an administrative unit. This module
only reports what the PDMA source printed as the station's river/group heading. The source publishes no
basin or catchment, so those stay null and `basin_context_status` is 'unresolved' (no basin hierarchy is invented).
"""

from __future__ import annotations

import re
from typing import Any, Optional

MAIN_RIVERS = {"INDUS", "JHELUM", "CHENAB", "RAVI", "SUTLEJ"}
# source headings that group torrents/nullahs rather than name a river
GROUP_HEADINGS = {"NULLAHS", "RAJANPUR HILL TORRENTS", "DG KHAN HILL TORRENTS"}


def hydrographic_context(river_reported: Optional[str]) -> dict[str, Any]:
    base = {"river_name": None, "river_heading_kind": None, "river_context_status": "unresolved",
            "basin_name": None, "catchment_name": None, "basin_context_status": "unresolved",
            "hydrographic_context_status": "unresolved", "hydrographic_note": None}
    r = (river_reported or "").strip()
    if not r:
        base["hydrographic_note"] = "no river heading reported"
        return base
    up = r.upper()
    if up in MAIN_RIVERS:
        kind = "river"
    elif up in GROUP_HEADINGS:
        kind = "torrent_or_nullah_group"
    else:
        # e.g. 'NULLAHS DATA SOURCE: F' -- PDF footer text bled into the heading; not a real river name
        base["hydrographic_note"] = f"reported heading {r!r} looks like a parsing artefact; not used as hydrographic context"
        return base
    base.update(river_name=r.title() if kind == "river" else r, river_heading_kind=kind,
                river_context_status="source_reported", hydrographic_context_status="source_reported",
                hydrographic_note="river/group heading as printed by the PDMA report; basin/catchment not published by the source")
    return base


def has_river_context(rec: dict) -> bool:
    return rec.get("river_context_status") in {"authoritative", "source_reported"} and rec.get("river_heading_kind") == "river"


_ = re  # (kept import-free of side effects)
