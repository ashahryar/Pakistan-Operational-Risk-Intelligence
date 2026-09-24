"""SUPARCO DisasterWatch parser.

Only `campaigns-live.json` is parsed: each entry is a live monitoring campaign (name, alert
level, start/end, optional GLIDE number, scope). `global-themes.json` is a map-layer catalogue
(vector-tile layer trees and styles) containing no hazard observations, so it is intentionally
not parsed. Nothing here is inferred beyond the source fields; `hazard_type` is derived only
from an explicit GLIDE number prefix (GLIDE is a published hazard-code standard).
"""

from __future__ import annotations

import json

from .artifacts import Artifact, failure

# GLIDE hazard codes (glidenumber.net standard). Only codes present in a record's own
# `glide_number` are ever used; a campaign without one keeps hazard_type=None.
GLIDE_HAZARD = {"FL": "flood", "EQ": "earthquake", "TC": "tropical_cyclone", "DR": "drought",
                "LS": "landslide", "WF": "wild_fire", "VO": "volcano", "ST": "storm", "EP": "epidemic"}

REQUIRED = ("id", "name")


def hazard_from_glide(glide_number):
    if not glide_number or "-" not in str(glide_number):
        return None
    return GLIDE_HAZARD.get(str(glide_number).split("-", 1)[0].upper())


def parse_campaigns(artifact: Artifact) -> tuple[list[dict], list[dict]]:
    records, failures = [], []
    try:
        payload = json.loads(artifact.path.read_bytes().decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return [], [failure("malformed_json", str(exc), artifact)]
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return [], [failure("unexpected_structure", "expected {'data': [...]}", artifact)]
    for entry in data:
        if not isinstance(entry, dict) or any(not entry.get(k) for k in REQUIRED):
            failures.append(failure("missing_required_field", f"campaign needs {REQUIRED}", artifact, entry))
            continue
        records.append({
            "source_record_id": f"campaign:{entry['id']}",
            "artifact": artifact.provenance(),
            "campaign_id": entry["id"], "slug": entry.get("slug"), "name": entry["name"],
            "description": entry.get("description"), "alert_level": entry.get("alert_level"),
            "starts_at": entry.get("starts_at"), "ends_at": entry.get("ends_at"),
            "last_updated": entry.get("last_updated"), "glide_number": entry.get("glide_number"),
            "hazard_type": hazard_from_glide(entry.get("glide_number")),
            "scope": entry.get("scope"), "is_live": entry.get("is_live"),
            "resource_count": entry.get("resource_count"),
        })
    return records, failures
