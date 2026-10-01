"""Task 22 -- leakage-safe feature engineering over real Gold datasets.

Every function is a pure `DataFrame/list[dict] -> DataFrame` transform (no I/O, no DB, no
wall-clock) so it is directly unit-testable with small synthetic frames and directly reusable
against the real Gold output on disk. Reuses Task 9's `scripts.forecasting.features` for the
gauge lag_1/lag_2/rolling_mean_3 primitives rather than reimplementing them -- see
pipeline/ml/feature_registry.py for the full feature catalogue and the leakage rule each column
follows.
"""

from __future__ import annotations

import pandas as pd

from scripts.forecasting.features import build_lag_features, chronological_split  # noqa: F401  (re-exported)

GAUGE_TARGET = "discharge_avg"


def _records_to_df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------- gauge (primary target)
def build_gauge_features(records: list[dict]) -> pd.DataFrame:
    """
    gold_gauge_daily -> one row per (station_name, date) with the full lag/rolling feature set
    documented in pipeline/ml/feature_registry.py ("gauge.*"), plus leakage-safe forward targets
    target_t_plus_1/3/7. Every feature column is computed via `.shift(1)` or later (never
    including the current row's own discharge_avg), and every target column is computed via
    `.shift(-N)` (strictly a FUTURE value, never fed back in as a feature).
    """
    if not records:
        return pd.DataFrame()

    df = _records_to_df(records)
    df = df.sort_values(["station_name", "date"]).reset_index(drop=True)

    # Reuse Task 9's primitive for lag_1/lag_2/rolling_mean_3 exactly (group_col/value_col/time_col
    # map onto Gold's daily-grain column names).
    df = build_lag_features(df, group_col="station_name", value_col=GAUGE_TARGET, time_col="date")

    grouped = df.groupby("station_name", sort=False)[GAUGE_TARGET]
    df["lag_3"] = grouped.shift(3)
    df["lag_7"] = grouped.shift(7)
    df["lag_14"] = grouped.shift(14)
    df["rolling_mean_7"] = grouped.apply(lambda s: s.shift(1).rolling(7, min_periods=7).mean()).reset_index(level=0, drop=True)
    df["rolling_mean_14"] = grouped.apply(lambda s: s.shift(1).rolling(14, min_periods=14).mean()).reset_index(level=0, drop=True)
    df["rolling_min_7"] = grouped.apply(lambda s: s.shift(1).rolling(7, min_periods=7).min()).reset_index(level=0, drop=True)
    df["rolling_max_7"] = grouped.apply(lambda s: s.shift(1).rolling(7, min_periods=7).max()).reset_index(level=0, drop=True)
    df["discharge_change"] = df["lag_1"] - df["lag_2"]
    df["discharge_pct_change"] = (df["lag_1"] - df["lag_2"]) / df["lag_2"]

    # Targets: strictly FUTURE values. Never used as model inputs -- see tests/ml/test_leakage.py.
    df["target_t_plus_1"] = grouped.shift(-1)
    df["target_t_plus_3"] = grouped.shift(-3)
    df["target_t_plus_7"] = grouped.shift(-7)

    return df


GAUGE_FEATURE_COLUMNS = ["lag_1", "lag_2", "lag_3", "lag_7", "lag_14", "rolling_mean_3", "rolling_mean_7",
                         "rolling_mean_14", "rolling_min_7", "rolling_max_7", "discharge_change", "discharge_pct_change"]


# ---------------------------------------------------------------- rainfall (observation-order)
def build_rainfall_features(records: list[dict]) -> pd.DataFrame:
    """
    gold_rainfall_daily -> observation-ORDER (never calendar-day) lag/rolling-sum features per
    station -- the series is event-driven (869 observations over only 78 distinct dates across
    16 months), too sparse for a calendar-day window to mean anything (see feature_registry.py).
    A missing `rainfall_total` stays NaN through every derived column -- never coerced to 0.
    """
    if not records:
        return pd.DataFrame()

    df = _records_to_df(records)
    df = df.sort_values(["station_name", "date"]).reset_index(drop=True)
    grouped = df.groupby("station_name", sort=False)["rainfall_total"]
    df["rainfall_lag_1"] = grouped.shift(1)
    df["rainfall_lag_2"] = grouped.shift(2)
    df["rainfall_lag_3"] = grouped.shift(3)
    df["rainfall_rolling_sum_3"] = grouped.apply(lambda s: s.shift(1).rolling(3, min_periods=3).sum()).reset_index(level=0, drop=True)
    return df


# ---------------------------------------------------------------- AQI (daily_district only)
def build_aqi_features(records: list[dict]) -> pd.DataFrame:
    """
    gold_air_quality -> daily lag/rolling AQI features, restricted to granularity=='daily_district'
    (the only AQI slice with genuine calendar continuity -- currently Lahore only, 350 consecutive
    days). station_snapshot rows (2 total, no history) are returned unfeatured, carrying only the
    registry's documented availability count.
    """
    if not records:
        return pd.DataFrame(), {"station_snapshot_count": 0}

    df = _records_to_df(records)
    daily = df[df["granularity"] == "daily_district"].sort_values(["geography_key", "date"]).reset_index(drop=True)
    station_snapshot_count = int((df["granularity"] == "station_snapshot").sum())

    if daily.empty:
        return daily, {"station_snapshot_count": station_snapshot_count}

    grouped = daily.groupby("geography_key", sort=False)["aqi_avg"]
    daily["aqi_lag_1"] = grouped.shift(1)
    daily["aqi_lag_7"] = grouped.shift(7)
    daily["aqi_rolling_mean_7"] = grouped.apply(lambda s: s.shift(1).rolling(7, min_periods=7).mean()).reset_index(level=0, drop=True)
    return daily, {"station_snapshot_count": station_snapshot_count}


# ---------------------------------------------------------------- hazard / disaster event features
def build_hazard_event_features(hazard_alerts: list[dict], disaster_events: list[dict], as_of_dates: list[str]) -> pd.DataFrame:
    """
    Builds (admin_unit_id, date) rows with strictly-historical event-count features
    (hazard.active_alert_count / recent_alert_count_7d / disaster.recent_event_count_30d).
    `as_of_dates` is the caller-supplied list of dates to compute features FOR (so this function
    never invents which dates matter) -- typically the distinct resolved-geography dates from
    gold_gauge_daily or another target dataset. Only alerts/events whose own effective date is
    <= the as-of date are ever counted (STEP 18 leakage test #5).
    """
    alerts = [a for a in hazard_alerts if a.get("resolution_status") == "resolved" and a.get("admin_unit_id") and a.get("issued_at")]
    events = [e for e in disaster_events if e.get("resolution_status") == "resolved" and e.get("admin_unit_id") and e.get("event_date")]

    admin_units = sorted({a["admin_unit_id"] for a in alerts} | {e["admin_unit_id"] for e in events})
    rows = []
    for uid in admin_units:
        unit_alerts = sorted(a["issued_at"][:10] for a in alerts if a["admin_unit_id"] == uid)
        unit_events = sorted(e["event_date"][:10] for e in events if e["admin_unit_id"] == uid)
        for date in sorted(as_of_dates):
            active = sum(1 for d in unit_alerts if d <= date)
            recent_7d = sum(1 for d in unit_alerts if _within_days(d, date, 7))
            recent_30d_events = sum(1 for d in unit_events if _within_days(d, date, 30))
            rows.append({"admin_unit_id": uid, "date": date, "active_alert_count": active,
                        "recent_alert_count_7d": recent_7d, "recent_event_count_30d": recent_30d_events})
    return pd.DataFrame(rows)


def _within_days(observed_date: str, as_of_date: str, window_days: int) -> bool:
    observed = pd.Timestamp(observed_date)
    as_of = pd.Timestamp(as_of_date)
    return observed <= as_of and (as_of - observed).days <= window_days
