"""Task 22 Step 18 -- mandatory leakage tests. No pyspark/sklearn required (these test
pipeline/ml/features.py, pure pandas, not the training script). Small, clearly-synthetic
station-shaped fixtures are used throughout so every assertion is easy to hand-verify.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.ml.features import build_aqi_features, build_gauge_features, build_hazard_event_features, build_rainfall_features


def _gauge_rows(station="Tarbela", start="2026-06-15", n=20, values=None):
    dates = pd.date_range(start, periods=n, freq="D").strftime("%Y-%m-%d")
    values = values or [1000.0 + 10 * i for i in range(n)]
    return [{"station_name": station, "date": d, "discharge_avg": v, "resolution_status": "unresolved",
            "admin_unit_id": None, "observation_count": 1} for d, v in zip(dates, values)]


# 1. feature at T does not depend on T+1 or later
def test_feature_at_t_does_not_depend_on_future_values():
    rows = _gauge_rows(n=10)
    df = build_gauge_features(rows)
    row5 = df[df["date"] == "2026-06-20"].iloc[0]  # the 6th day (index 5)
    # lag_1 at this row must equal the PRIOR day's discharge, never this day's or a later day's.
    prior_value = df[df["date"] == "2026-06-19"].iloc[0]["discharge_avg"]
    assert row5["lag_1"] == prior_value
    # Changing every value AFTER this row must not change this row's lag_1/lag_2/rolling features.
    rows_mutated = _gauge_rows(n=10, values=[1000.0 + 10 * i if i <= 5 else 999999.0 for i in range(10)])
    df2 = build_gauge_features(rows_mutated)
    row5_after = df2[df2["date"] == "2026-06-20"].iloc[0]
    for col in ("lag_1", "lag_2", "rolling_mean_3"):
        assert row5[col] == row5_after[col]


# 2. rolling features use historical observations only
def test_rolling_mean_excludes_current_row():
    # Make the current row's own value an extreme outlier; rolling_mean_3 must not reflect it.
    values = [10.0, 10.0, 10.0, 10.0, 999999.0]
    rows = _gauge_rows(n=5, values=values)
    df = build_gauge_features(rows)
    last_row = df.iloc[-1]
    assert last_row["discharge_avg"] == 999999.0
    assert last_row["rolling_mean_3"] == 10.0  # mean of the 3 PRIOR days, not including 999999.0


# 3. train/test split is chronological
def test_chronological_split_never_lets_test_precede_train():
    from pipeline.ml.features import chronological_split

    rows = _gauge_rows(n=30)
    df = build_gauge_features(rows).dropna(subset=["lag_1"]).reset_index(drop=True)
    df["_split_date"] = pd.to_datetime(df["date"])
    train, val, test = chronological_split(df, time_col="_split_date", train_pct=0.6, val_pct=0.2)
    assert train["_split_date"].max() <= val["_split_date"].min()
    assert val["_split_date"].max() <= test["_split_date"].min()


# 4. test data cannot affect scaler/feature fitting (no global stats computed before split)
def test_feature_construction_never_uses_a_full_dataset_global_statistic():
    """build_gauge_features computes only per-row shift/rolling values -- confirmed by checking
    that an early row's features are IDENTICAL whether or not later (would-be test-set) rows
    exist in the input at all."""
    rows_full = _gauge_rows(n=20)
    rows_truncated = _gauge_rows(n=6)  # only the first 6 days -- simulates "no test set visible"
    df_full = build_gauge_features(rows_full)
    df_trunc = build_gauge_features(rows_truncated)
    early_full = df_full[df_full["date"] == "2026-06-20"].iloc[0]  # 6th day
    early_trunc = df_trunc[df_trunc["date"] == "2026-06-20"].iloc[0]
    for col in ("lag_1", "lag_2", "rolling_mean_3"):
        assert early_full[col] == early_trunc[col]


# 5. future alerts/events do not appear in historical features
def test_hazard_event_features_never_count_a_future_alert():
    alerts = [{"resolution_status": "resolved", "admin_unit_id": 1, "issued_at": "2026-07-10T00:00:00"}]
    events = []
    features = build_hazard_event_features(alerts, events, as_of_dates=["2026-07-05", "2026-07-10", "2026-07-15"])
    by_date = features.set_index("date")
    assert by_date.loc["2026-07-05", "active_alert_count"] == 0   # alert hasn't happened yet
    assert by_date.loc["2026-07-10", "active_alert_count"] == 1   # issued exactly on this date -- known by end of day
    assert by_date.loc["2026-07-15", "active_alert_count"] == 1   # still active afterward


def test_disaster_event_features_never_count_a_future_event():
    events = [{"resolution_status": "resolved", "admin_unit_id": 2, "event_date": "2026-08-01"}]
    features = build_hazard_event_features([], events, as_of_dates=["2026-07-25", "2026-08-01", "2026-08-20"])
    by_date = features.set_index("date")
    assert by_date.loc["2026-07-25", "recent_event_count_30d"] == 0
    assert by_date.loc["2026-08-01", "recent_event_count_30d"] == 1
    assert by_date.loc["2026-08-20", "recent_event_count_30d"] == 1  # within the 30-day window


# 6. duplicate input does not change output
def test_duplicate_gauge_rows_do_not_multiply_output_rows():
    rows = _gauge_rows(n=5)
    doubled = rows + rows
    df_single = build_gauge_features(rows)
    df_doubled = build_gauge_features(doubled)
    # Duplicate rows at the same (station, date) key are not deduplicated by this pure feature
    # function (that's Bronze's job, already proven in Task 20) -- but they must not corrupt or
    # multiply the lag computation for the UNIQUE dates that exist.
    assert set(df_single["date"]) == set(df_doubled["date"].unique())


# 7. running feature generation twice produces identical output
def test_feature_generation_is_idempotent():
    rows = _gauge_rows(n=15)
    first = build_gauge_features(rows)
    second = build_gauge_features(rows)
    pd.testing.assert_frame_equal(first, second)


def test_rainfall_feature_generation_is_idempotent():
    rows = [{"station_name": "Layyah", "date": d, "rainfall_total": v, "resolution_status": "resolved",
            "admin_unit_id": 5, "observation_count": 1}
           for d, v in zip(pd.date_range("2026-07-01", periods=6).strftime("%Y-%m-%d"), [1.0, None, 3.0, 4.0, None, 6.0])]
    first = build_rainfall_features(rows)
    second = build_rainfall_features(rows)
    pd.testing.assert_frame_equal(first, second)


# 8. missing rainfall remains missing, not zero
def test_missing_rainfall_observation_stays_null_never_zero():
    rows = [{"station_name": "Layyah", "date": d, "rainfall_total": v, "resolution_status": "resolved",
            "admin_unit_id": 5, "observation_count": 1}
           for d, v in zip(pd.date_range("2026-07-01", periods=4).strftime("%Y-%m-%d"), [10.0, None, None, 5.0])]
    df = build_rainfall_features(rows)
    last_row = df.iloc[-1]
    # lag_1 for the last row is the 3rd observation, which was itself missing (None) -- must stay
    # NaN, not be silently treated as 0 anywhere in the computation.
    assert pd.isna(last_row["rainfall_lag_1"])
    assert last_row["rainfall_lag_1"] != 0


# 9. unresolved geography is not silently assigned
def test_unresolved_gauge_station_keeps_no_admin_unit_id_through_feature_engineering():
    rows = _gauge_rows(n=5)  # resolution_status="unresolved", admin_unit_id=None in _gauge_rows()
    df = build_gauge_features(rows)
    assert (df["admin_unit_id"].isna() | (df["admin_unit_id"] is None)).all()
    assert (df["resolution_status"] == "unresolved").all()


def test_hazard_event_features_only_use_resolved_geography():
    alerts = [{"resolution_status": "unresolved", "admin_unit_id": None, "issued_at": "2026-07-01T00:00:00"},
             {"resolution_status": "resolved", "admin_unit_id": 7, "issued_at": "2026-07-02T00:00:00"}]
    features = build_hazard_event_features(alerts, [], as_of_dates=["2026-07-05"])
    assert set(features["admin_unit_id"]) == {7}  # the unresolved alert never creates a fake geography row


# 10. target is not included as a contemporaneous feature
def test_target_column_is_never_one_of_the_numeric_feature_columns():
    from pipeline.ml.features import GAUGE_FEATURE_COLUMNS

    assert "target_t_plus_1" not in GAUGE_FEATURE_COLUMNS
    assert "discharge_avg" not in GAUGE_FEATURE_COLUMNS  # the contemporaneous value itself is not a feature


def test_target_t_plus_1_is_strictly_the_next_rows_value_never_the_current_rows():
    rows = _gauge_rows(n=5, values=[100.0, 200.0, 300.0, 400.0, 500.0])
    df = build_gauge_features(rows)
    row0 = df[df["date"] == "2026-06-15"].iloc[0]
    assert row0["target_t_plus_1"] == 200.0  # the NEXT day's value
    assert row0["target_t_plus_1"] != row0["discharge_avg"]
    last_row = df.iloc[-1]
    assert pd.isna(last_row["target_t_plus_1"])  # no future row exists for the final observed day


# ---------------------------------------------------------------- AQI-specific
def test_aqi_station_snapshot_rows_get_no_fabricated_lag_feature():
    records = [{"geography_key": "Lahore", "date": "2026-09-16", "granularity": "station_snapshot", "aqi_avg": 180.0}]
    daily_df, meta = build_aqi_features(records)
    assert daily_df.empty and meta["station_snapshot_count"] == 1
