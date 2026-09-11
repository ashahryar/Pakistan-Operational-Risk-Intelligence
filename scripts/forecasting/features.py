"""
scripts/forecasting/features.py

Phase 1 / Task 9 (ADR-0001) -- pure, DB-free feature engineering and
chronological train/validation/test splitting for the gauge discharge
baseline forecast.

Every function here is a pure function of its DataFrame argument: no
database connection, no file I/O, no import-time side effect. This is
what makes tests/forecasting/test_features.py able to test them with
small, deterministic, in-file DataFrames -- see that file's docstring
for why those synthetic frames are for testing the *transformation
logic* only and are never fed into the actual trained model or
reported as real historical data.
"""

from __future__ import annotations

import pandas as pd

# Columns added by build_lag_features(), in order. Exposed as a constant
# so callers/tests don't have to hard-code the list twice.
LAG_FEATURE_COLUMNS = ["lag_1", "lag_2", "rolling_mean_3"]


def build_lag_features(
    df: pd.DataFrame,
    group_col: str = "station",
    value_col: str = "discharge_cusecs",
    time_col: str = "report_datetime",
) -> pd.DataFrame:
    """
    Returns a NEW DataFrame (input is not mutated) with three added
    columns, computed per `group_col` group in ascending `time_col`
    order:

      lag_1          -- the group's previous reading
      lag_2           -- the group's reading before that
      rolling_mean_3  -- mean of the group's 3 most recent PRIOR
                          readings (lag_1..lag_3), never including the
                          current row's own value -- this must stay a
                          leakage-free feature, computable at the
                          moment a real forecast would be made.

    Rows where a feature can't be computed yet (not enough prior
    history in that group) get NaN in that column. This function does
    not drop those rows -- callers decide how to handle incomplete
    rows (train.py drops them before fitting), so this function's
    behavior on short/edge-case groups stays directly testable.
    """
    out = df.sort_values([group_col, time_col]).reset_index(drop=True).copy()

    grouped_value = out.groupby(group_col, sort=False)[value_col]
    out["lag_1"] = grouped_value.shift(1)
    out["lag_2"] = grouped_value.shift(2)
    out["rolling_mean_3"] = (
        out.groupby(group_col, sort=False)[value_col]
        .apply(lambda s: s.shift(1).rolling(window=3, min_periods=3).mean())
        .reset_index(level=0, drop=True)
    )

    return out


def chronological_split(
    df: pd.DataFrame,
    time_col: str = "report_datetime",
    train_pct: float = 0.70,
    val_pct: float = 0.15,
):
    """
    Splits `df` into (train, val, test) DataFrames using GLOBAL time
    percentile cutoffs on `time_col` -- never a random split, and never
    a per-group split (a single pair of cutoffs is applied to every
    row regardless of which station/group it belongs to, so no row in
    `test` can have an earlier timestamp than any row in `train`).

    train_pct is the fraction of (sorted-by-time) rows assigned to
    train; val_pct is the next slice; the remainder is test. Cutoffs
    are computed as quantiles of `time_col`, so:

      train: time_col <= quantile(train_pct)
      val:   quantile(train_pct) < time_col <= quantile(train_pct+val_pct)
      test:  time_col > quantile(train_pct+val_pct)

    Raises ValueError on an empty `df` or an out-of-range split.
    """
    if df.empty:
        raise ValueError("chronological_split: df is empty")
    if not (0 < train_pct < 1):
        raise ValueError(f"chronological_split: train_pct out of range: {train_pct}")
    if not (0 <= val_pct < 1):
        raise ValueError(f"chronological_split: val_pct out of range: {val_pct}")
    if train_pct + val_pct >= 1:
        raise ValueError(
            f"chronological_split: train_pct + val_pct must be < 1 "
            f"(got {train_pct} + {val_pct} = {train_pct + val_pct})"
        )

    ordered = df.sort_values(time_col).reset_index(drop=True)
    times = ordered[time_col]

    train_cutoff = times.quantile(train_pct)
    test_cutoff = times.quantile(train_pct + val_pct)

    train = ordered[ordered[time_col] <= train_cutoff].reset_index(drop=True)
    val = ordered[
        (ordered[time_col] > train_cutoff) & (ordered[time_col] <= test_cutoff)
    ].reset_index(drop=True)
    test = ordered[ordered[time_col] > test_cutoff].reset_index(drop=True)

    return train, val, test
