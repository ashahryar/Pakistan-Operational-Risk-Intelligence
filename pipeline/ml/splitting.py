"""Task 33 -- strict, purged, time-based train / validation / test splitting. Never random.

Boundaries are dates taken from the usable rows' TARGET dates (70 % / 85 % points of the sorted unique target dates). Each split's labels lie entirely
inside that split's own period, and a split's origins start after the previous split's period ended:
    train      : target_date <= train_end
    validation : origin_date  >  train_end   and target_date <= val_end
    test       : origin_date  >  val_end
Rows whose origin is inside a period but whose target falls in the next one are PURGED (counted, never used): otherwise a training label would be a
validation-period observation (target leakage across the boundary). Features of later splits legitimately use earlier observations (they are past by then).
"""

from __future__ import annotations

import pandas as pd


def temporal_split(frame: pd.DataFrame, train_frac: float = 0.70, val_frac: float = 0.15) -> dict:
    use = frame[frame["usable"]]
    if use.empty:
        return {"train": use, "validation": use, "test": use, "boundaries": None, "purged": 0}
    dates = sorted(use["target_date"].unique())
    train_end = dates[min(len(dates) - 1, max(0, int(len(dates) * train_frac) - 1))]
    val_end = dates[min(len(dates) - 1, max(0, int(len(dates) * (train_frac + val_frac)) - 1))]
    train = use[use["target_date"] <= train_end]
    val = use[(use["origin_date"] > train_end) & (use["target_date"] <= val_end)]
    test = use[use["origin_date"] > val_end]
    purged = len(use) - len(train) - len(val) - len(test)

    def rng(df, col):
        return (pd.Timestamp(df[col].min()).date().isoformat(), pd.Timestamp(df[col].max()).date().isoformat()) if len(df) else (None, None)

    return {"train": train, "validation": val, "test": test, "purged": int(purged),
            "boundaries": {"train_end": pd.Timestamp(train_end).date().isoformat(), "validation_end": pd.Timestamp(val_end).date().isoformat(),
                           "train_origin_range": rng(train, "origin_date"), "train_target_range": rng(train, "target_date"),
                           "validation_origin_range": rng(val, "origin_date"), "validation_target_range": rng(val, "target_date"),
                           "test_origin_range": rng(test, "origin_date"), "test_target_range": rng(test, "target_date")}}


def assert_no_overlap(split: dict) -> None:
    """Raises AssertionError if any leakage across the boundaries is possible (also used by the tests)."""
    tr, va, te = split["train"], split["validation"], split["test"]
    b = split["boundaries"]
    if b is None:
        return
    train_end, val_end = pd.Timestamp(b["train_end"]), pd.Timestamp(b["validation_end"])
    if len(tr):
        assert tr["target_date"].max() <= train_end
    if len(va):
        assert va["origin_date"].min() > train_end and va["target_date"].max() <= val_end
    if len(te):
        assert te["origin_date"].min() > val_end
    if len(tr) and len(va):
        assert tr["target_date"].max() <= train_end < va["origin_date"].min()
    if len(va) and len(te):
        assert va["target_date"].max() <= val_end < te["origin_date"].min()
