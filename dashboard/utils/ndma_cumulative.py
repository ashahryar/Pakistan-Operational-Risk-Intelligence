"""Task 40 -- NDMA situation reports state CUMULATIVE figures (deaths, injured, houses ... since the start of the monsoon window),
so summing them across reports multiplies the real total. This helper turns a cumulative series into the non-negative increments
between reports, using the per-province RUNNING MAXIMUM so that parser dips or downward revisions never create negative or repeated counts.

Properties (tested): for each province and column, the sum of the increments equals the peak reported value; a missing value stays missing
(never zero); nothing is invented. The as-reported running maximum is kept in `<col>_cumulative`.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd


def cumulative_to_increments(df: pd.DataFrame, cols: Iterable[str], group: str = "province", date: str = "report_date") -> pd.DataFrame:
    out = df.sort_values([group, date]).copy()
    for col in cols:
        if col not in out:
            continue
        cum = out.groupby(group)[col].cummax()                      # running maximum; NaN rows stay NaN (skipna)
        prev = cum.groupby(out[group]).ffill().groupby(out[group]).shift()
        out[f"{col}_cumulative"] = cum
        out[col] = (cum - prev.fillna(0)).where(cum.notna())
    return out.sort_values(date).reset_index(drop=True)


def peak_totals(df: pd.DataFrame, cols: Iterable[str], group: str = "province") -> dict:
    """National totals = sum over provinces of the peak cumulative value (None when the column has no value at all)."""
    res = {}
    for c in cols:
        s = df.groupby(group)[c].max()
        res[c] = None if s.dropna().empty else float(s.sum())
    return res
