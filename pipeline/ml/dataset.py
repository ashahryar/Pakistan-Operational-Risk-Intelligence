"""Task 33 -- dataset construction and leakage-safe feature engineering for the prediction layer (pure pandas, no I/O, no wall clock).

Time convention. A training row has an ORIGIN date D (the *feature cutoff*, inclusive: the observation of day D is known at the end of day D) and a
TARGET date D + h (h = horizon in days). Every feature at D is a function of observations dated <= D only; the label is the observation dated exactly
D + h. Features never use anything later than D, the label of a row is never an input to any feature of any other row that precedes it in time, and no
statistic is computed over the whole series (no global scaling here; scaling lives inside the model pipeline and is fit on the training split only).

Missing data. The series is placed on the complete calendar-day grid between its first and last observation. A missing day stays NaN: it is never
interpolated, forward-filled or zero-filled. A feature that needs a missing day is NaN, and a row with any NaN feature or a missing label is NOT usable
(it is kept in the frame with `drop_reason` so its impact can be counted). Only real observations are ever labels.

Not inputs: documents / RAG content, risk-engine outputs, manually created labels, anything dated after the origin.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, Optional

import numpy as np
import pandas as pd

LAGS = (0, 1, 2, 6, 13)                 # value at D - k  (k = 0 is the origin day itself)
ROLL_WINDOWS = (3, 7, 14)               # mean over the w calendar days ending at D (all w days must be observed)
FEATURE_COLUMNS = [f"lag_{k}" for k in LAGS] + [f"rolling_mean_{w}" for w in ROLL_WINDOWS] + ["rolling_std_7", "delta_1"]
FRAME_COLUMNS = ["entity_id", "origin_date", "target_date", "horizon_days", *FEATURE_COLUMNS, "target", "usable", "drop_reason"]


def build_daily_series(records: Iterable[dict], entity_key: str, date_key: str, value_key: str) -> pd.DataFrame:
    """Records -> one row per (entity, calendar day) on the complete day grid; `value` is NaN where no real observation exists.
    Duplicate (entity, date) records are averaged (the Gold layer already aggregates per day, so this is a guard, not a method)."""
    df = pd.DataFrame.from_records(list(records))
    if df.empty:
        return pd.DataFrame(columns=["entity_id", "date", "value", "observed"])
    df = df[[entity_key, date_key, value_key]].rename(columns={entity_key: "entity_id", date_key: "date", value_key: "value"})
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["entity_id", "date"])
    df = df.groupby(["entity_id", "date"], as_index=False)["value"].mean()
    out = []
    for eid, g in df.groupby("entity_id", sort=True):
        grid = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        s = g.set_index("date")["value"].reindex(grid)
        out.append(pd.DataFrame({"entity_id": eid, "date": grid, "value": s.to_numpy(), "observed": s.notna().to_numpy()}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["entity_id", "date", "value", "observed"])


def history_summary(series: pd.DataFrame) -> dict[str, dict]:
    """Per entity: first/last observed date and number of observed days (what the minimum-history rule is checked against)."""
    out = {}
    for eid, g in series.groupby("entity_id", sort=True):
        obs = g[g["observed"]]
        out[str(eid)] = {"first_date": obs["date"].min().date().isoformat() if len(obs) else None,
                         "last_date": obs["date"].max().date().isoformat() if len(obs) else None, "observed_days": int(len(obs)),
                         "calendar_days": int(len(g)), "missing_days": int(len(g) - len(obs))}
    return out


def _features_for(values: pd.Series) -> pd.DataFrame:
    """Features at every origin of one entity's calendar-grid value series. Uses only values at or before each origin."""
    f = pd.DataFrame(index=values.index)
    for k in LAGS:
        f[f"lag_{k}"] = values.shift(k)
    for w in ROLL_WINDOWS:
        f[f"rolling_mean_{w}"] = values.rolling(window=w, min_periods=w).mean()          # window ends at the origin day (inclusive)
    f["rolling_std_7"] = values.rolling(window=7, min_periods=7).std()
    f["delta_1"] = values - values.shift(1)
    return f[FEATURE_COLUMNS]


def build_supervised(series: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """One row per (entity, origin day): features at the origin, the observed value at origin + horizon as `target`, and `usable` / `drop_reason`."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1 day")
    frames = []
    for eid, g in series.groupby("entity_id", sort=True):
        g = g.sort_values("date")
        vals = pd.Series(g["value"].to_numpy(dtype=float), index=pd.DatetimeIndex(g["date"]))
        feats = _features_for(vals)
        target = vals.shift(-horizon)                                                   # strictly a FUTURE observation, never fed back as a feature
        row = feats.copy()
        row.insert(0, "entity_id", eid)
        row.insert(1, "origin_date", vals.index)
        row.insert(2, "target_date", vals.index + pd.Timedelta(days=horizon))
        row.insert(3, "horizon_days", horizon)
        row["target"] = target.to_numpy()
        no_feature = feats.isna().any(axis=1).to_numpy()
        no_target = row["target"].isna().to_numpy()
        reason = np.where(no_feature & no_target, "missing_feature_and_target", np.where(no_feature, "missing_or_insufficient_history", np.where(no_target, "target_not_observed", "")))
        row["usable"] = ~(no_feature | no_target)
        row["drop_reason"] = reason
        frames.append(row.reset_index(drop=True))
    if not frames:
        return pd.DataFrame(columns=FRAME_COLUMNS)
    return pd.concat(frames, ignore_index=True)[FRAME_COLUMNS]


def missing_data_impact(frame: pd.DataFrame) -> dict:
    """How many candidate origins were lost and why (never silently dropped)."""
    total = int(len(frame))
    reasons = frame.loc[~frame["usable"], "drop_reason"].value_counts().to_dict()
    return {"candidate_rows": total, "usable_rows": int(frame["usable"].sum()), "dropped_rows": int((~frame["usable"]).sum()),
            "dropped_share": round(float((~frame["usable"]).mean()), 4) if total else None, "dropped_by_reason": {k: int(v) for k, v in reasons.items()}}


def latest_origin_features(series: pd.DataFrame, entity_id, as_of: pd.Timestamp) -> Optional[pd.Series]:
    """Features at `as_of` for one entity using only observations dated <= as_of; None if any feature is unavailable (never imputed)."""
    g = series[(series["entity_id"] == entity_id) & (series["date"] <= as_of)].sort_values("date")
    if g.empty or g["date"].max() != as_of:
        return None
    vals = pd.Series(g["value"].to_numpy(dtype=float), index=pd.DatetimeIndex(g["date"]))
    f = _features_for(vals).iloc[-1]
    return None if f.isna().any() else f


def data_fingerprint(series: pd.DataFrame, extra: Optional[dict] = None) -> str:
    """Stable hash of the observed data (+ parameters): the same data and settings always give the same model version."""
    obs = series[series["observed"]].sort_values(["entity_id", "date"])
    payload = [(str(r.entity_id), r.date.date().isoformat(), round(float(r.value), 6)) for r in obs.itertuples()]
    return hashlib.sha256(json.dumps([payload, extra or {}], sort_keys=True).encode("utf-8")).hexdigest()
