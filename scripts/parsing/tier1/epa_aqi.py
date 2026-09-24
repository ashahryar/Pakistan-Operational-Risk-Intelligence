"""EPA Punjab AQI parsers (districts list, per-district station snapshot, city calendar).

Fields are passed through exactly as the API states them (pollutants arrive as numeric strings;
numeric coercion happens once, in the canonical layer). The station snapshot carries no
measurement timestamp, so `observed_at` is the artifact's retrieval time and is labelled as such.
The API states no pollutant units, so none are asserted.
"""

from __future__ import annotations

import json

from .artifacts import Artifact, failure

POLLUTANTS = ("pm25", "pm10", "co", "so2", "no2", "o3")


def _load(artifact: Artifact):
    try:
        return json.loads(artifact.path.read_bytes().decode("utf-8")), None
    except (ValueError, UnicodeDecodeError) as exc:
        return None, [failure("malformed_json", str(exc), artifact)]


def parse_districts(artifact: Artifact):
    payload, err = _load(artifact)
    if err:
        return [], err
    names = payload.get("districts") if isinstance(payload, dict) else None
    if not isinstance(names, list):
        return [], [failure("unexpected_structure", "expected {'districts': [...]}", artifact)]
    return [{"source_record_id": f"district:{name}", "artifact": artifact.provenance(), "district": name}
            for name in names if isinstance(name, str) and name.strip()], []


def parse_station_snapshot(artifact: Artifact):
    payload, err = _load(artifact)
    if err:
        return [], err
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return [], [failure("unexpected_structure", "expected {'data': [...], 'district': ...}", artifact)]
    district, records, failures = payload.get("district"), [], []
    for row in payload["data"]:
        if not isinstance(row, dict) or not row.get("station_name"):
            failures.append(failure("missing_station_name", "station row without station_name", artifact, row))
            continue
        record = {"source_record_id": f"station:{district}:{row['station_name']}:{artifact.retrieved_at}",
                  "artifact": artifact.provenance(), "district": district, "station_name": row["station_name"],
                  "aqi": row.get("aqi"), "major_pollutant": row.get("major_pollutant"),
                  "observed_at": artifact.retrieved_at, "observed_at_basis": "retrieved_at"}
        for pollutant in POLLUTANTS:
            record[pollutant] = row.get(pollutant)
        records.append(record)
    return records, failures


def parse_calendar(artifact: Artifact):
    payload, err = _load(artifact)
    if err:
        return [], err
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return [], [failure("unexpected_structure", "expected {'data': {year: {month: ...}}}", artifact)]
    district, records, failures = payload.get("district"), [], []
    for year in sorted(payload["data"]):
        for month in sorted(payload["data"][year], key=lambda m: int(m) if str(m).isdigit() else 0):
            days = (payload["data"][year][month] or {}).get("days") or {}
            for day_key in sorted(days, key=lambda d: int(d) if str(d).isdigit() else 0):
                day = days[day_key]
                if not isinstance(day, dict) or not day.get("date"):
                    failures.append(failure("missing_date", f"calendar day {year}-{month}-{day_key} has no date",
                                            artifact, day))
                    continue
                records.append({"source_record_id": f"aqi-calendar:{district}:{day['date']}",
                                "artifact": artifact.provenance(), "district": district, "date": day["date"],
                                "aqi": day.get("aqi"), "station_count": day.get("stationCount"),
                                "stations_reporting": day.get("stations")})
    return records, failures
