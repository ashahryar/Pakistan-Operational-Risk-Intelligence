"""Reusable, leakage-safe signal normalizations.

Every function documents: source field, transformation, direction, missing behavior, history
requirement and leakage rule. Missing (None) is NEVER coerced to zero; a genuine 0 stays 0.
"""

from __future__ import annotations

from typing import Optional, Sequence


def percentile_rank_strict(value: Optional[float], prior_values: Sequence[Optional[float]],
                           min_history: int) -> Optional[float]:
    """fraction of PRIOR observations strictly below `value`.
    direction: higher_is_more_risk. missing: value None -> None. history: needs >= min_history
    non-null prior values, else None (INSUFFICIENT_HISTORY). leakage: caller must pass only
    observations dated strictly before the cell's date (see history_before)."""
    if value is None:
        return None
    prior = [p for p in prior_values if p is not None]
    if len(prior) < min_history or not prior:
        return None
    return sum(1 for p in prior if p < value) / len(prior)


def min_max(value: Optional[float], lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    """(value-lo)/(hi-lo) clipped to [0,1]; None if any input is None or hi == lo."""
    if value is None or lo is None or hi is None or hi == lo:
        return None
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def binary_signal(present: Optional[bool]) -> Optional[float]:
    """1.0 if an alert/event is observed present; None (NOT 0.0) when presence is unknown."""
    if present is None:
        return None
    return 1.0 if present else 0.0


def history_before(series: dict[str, Optional[float]], date: str) -> list[Optional[float]]:
    """Values of a date->value series with date STRICTLY earlier than `date` (ISO strings)."""
    return [v for d, v in sorted(series.items()) if d < date]


def count_in_window(dates: Sequence[str], end_date: str, window_days: int) -> int:
    """number of ISO dates d with end_date-window_days < d <= end_date (future dates excluded)."""
    import datetime as _dt
    end = _dt.date.fromisoformat(end_date)
    start = end - _dt.timedelta(days=window_days)
    return sum(1 for d in dates if start < _dt.date.fromisoformat(d[:10]) <= end)
