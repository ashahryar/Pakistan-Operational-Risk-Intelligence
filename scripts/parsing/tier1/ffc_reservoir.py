"""FFC homepage reservoir-level parser.

The only structured content is one sentence of homepage text, e.g.
"Reservoirs Level Updated: (16, September 2026 @ 0600 Hours) Tarble Level 1542.04 feet
(Live storage 5.122 MAF) Mangla Level ... Chashma Level ...". No inflow/outflow/capacity figures
exist on the page, so none are produced. The source spells Tarbela "Tarble"; the original
spelling is preserved and the canonical name is set through an explicit, documented alias.
The page states no timezone, so `observed_at` is naive.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .artifacts import Artifact, failure

NAME_ALIASES = {"tarble": "Tarbela", "tarbela": "Tarbela", "mangla": "Mangla", "chashma": "Chashma"}
_HEADER = re.compile(r"Reservoirs Level Updated:\s*\((\d{1,2}),?\s+([A-Za-z]+)\s+(\d{4})\s*@\s*(\d{4})\s*Hours\)")
_RESERVOIR = re.compile(r"([A-Za-z]+)\s+Level\s+([\d.]+)\s+feet\s+\(Live storage\s+([\d.]+)\s+MAF\)")
_COMBINED = re.compile(r"Combined Live Storage of three Reservoirs:\s*([\d.]+)\s*MAF")


def parse_reservoir_html(artifact: Artifact):
    text = BeautifulSoup(artifact.path.read_bytes().decode("utf-8", errors="replace"), "html.parser").get_text(" ")
    text = re.sub(r"\s+", " ", text)
    header = _HEADER.search(text)
    if not header:
        return [], [failure("reservoir_sentence_not_found", "no 'Reservoirs Level Updated' sentence", artifact)]
    day, month, year, hhmm = header.groups()
    try:
        observed = datetime.strptime(f"{day} {month} {year} {hhmm}", "%d %B %Y %H%M").isoformat()
    except ValueError as exc:
        return [], [failure("invalid_observation_time", str(exc), artifact, header.group(0))]
    sentence = text[header.end(): header.end() + 600]
    combined = _COMBINED.search(sentence)
    records, failures = [], []
    for name, level, storage in _RESERVOIR.findall(sentence):
        canonical = NAME_ALIASES.get(name.lower())
        if canonical is None:
            failures.append(failure("unknown_reservoir", f"unrecognised reservoir name {name!r}", artifact, name))
            continue
        records.append({"source_record_id": f"reservoir:{canonical}:{observed}", "artifact": artifact.provenance(),
                        "reservoir_name": canonical, "reservoir_name_original": name, "observed_at": observed,
                        "water_level": level, "water_level_unit": "ft", "live_storage": storage,
                        "live_storage_unit": "MAF",
                        "combined_live_storage": combined.group(1) if combined else None})
    if not records and not failures:
        failures.append(failure("no_reservoir_levels", "sentence found but no reservoir level entries", artifact))
    return records, failures
