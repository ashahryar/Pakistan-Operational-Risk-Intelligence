"""Small, lossless-friendly normalizers shared by canonical adapters."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

NULL_MARKERS = {"", "-", "n/a", "na", "null", "none", "not available", "not reported", "unavailable"}


def normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    result = re.sub(r"\s+", " ", str(value)).strip()
    return result or None


def normalize_number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = normalize_string(value)
    if text is None or text.lower() in NULL_MARKERS:
        return None
    if not re.fullmatch(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|[-+]?\d+(?:\.\d+)?", text):
        return None
    number = float(text.replace(",", ""))
    return int(number) if number.is_integer() else number


def normalize_timestamp(value: Any) -> str | None:
    """Return ISO 8601, retaining naive timestamps when source timezone is unknown."""
    text = normalize_string(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass
    for fmt in ("%d %B %Y", "%d %b %Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_unit(value: Any, allowed: set[str] | None = None) -> str | None:
    unit = normalize_string(value)
    if unit is None:
        return None
    aliases = {"mm": "mm", "millimetres": "mm", "millimeters": "mm", "ft": "ft", "feet": "ft", "cusecs": "cusecs"}
    normalized = aliases.get(unit.lower(), unit)
    return normalized if allowed is None or normalized in allowed else None
