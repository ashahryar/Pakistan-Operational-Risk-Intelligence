"""
tests/forecasting/test_features.py

Phase 1 / Task 9 (ADR-0001) -- deterministic tests for
scripts/forecasting/features.py's two pure functions:
build_lag_features() and chronological_split().

All fixtures in THIS file are deliberately clearly-synthetic small
integer/date sequences (e.g. [10, 20, 30, 40, 50]) -- they test the
*transformation logic* in isolation and are never presented as real
observations, never fed into the actual trained model, and never used
to compute or report a real metric. The real-data fixture used for
end-to-end prediction-schema testing lives in
tests/fixtures/forecasting/ and is exercised by
test_prediction_schema.py instead -- see tests/fixtures/README.md for
its provenance.
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.forecasting.features import build_lag_features, chronological_split


# ==========================================================
# build_lag_features
# ==========================================================

def _single_station_df():
    return pd.DataFrame(
        {
            "station": ["A"] * 5,
            "report_datetime": pd.date_range("2026-01-01", periods=5, freq="D"),
            "discharge_cusecs": [10, 20, 30, 40, 50],
        }
    )


def test_build_lag_features_lag_columns():
    result = build_lag_features(_single_station_df())
    assert pd.isna(result["lag_1"].iloc[0])
    assert list(result["lag_1"])[1:] == [10, 20, 30, 40]
    assert pd.isna(result["lag_2"].iloc[0])
    assert pd.isna(result["lag_2"].iloc[1])
    assert list(result["lag_2"])[2:] == [10, 20, 30]


def test_build_lag_features_rolling_mean_3():
    result = build_lag_features(_single_station_df())
    # rolling_mean_3 is the mean of the 3 most recent PRIOR readings --
    # never including the row's own value. For values [10,20,30,40,50]:
    #   row0,1,2: not enough prior history -> NaN
    #   row3 (value 40): prior 3 = [10,20,30] -> mean 20
    #   row4 (value 50): prior 3 = [20,30,40] -> mean 30
    assert pd.isna(result["rolling_mean_3"].iloc[0])
    assert pd.isna(result["rolling_mean_3"].iloc[1])
    assert pd.isna(result["rolling_mean_3"].iloc[2])
    assert result["rolling_mean_3"].iloc[3] == pytest.approx(20.0)
    assert result["rolling_mean_3"].iloc[4] == pytest.approx(30.0)


def test_build_lag_features_short_group_never_gets_rolling_mean():
    df = pd.DataFrame(
        {
            "station": ["A", "A"],
            "report_datetime": pd.date_range("2026-01-01", periods=2, freq="D"),
            "discharge_cusecs": [10, 20],
        }
    )
    result = build_lag_features(df)
    assert result["rolling_mean_3"].isna().all()


def test_build_lag_features_no_cross_group_leakage():
    """
    Station B's readings (even an earlier one) must never leak into
    station A's lag_1/lag_2/rolling_mean_3.
    """
    df = pd.DataFrame(
        {
            "station": ["B", "A", "A", "A"],
            "report_datetime": pd.to_datetime(
                ["2025-01-01", "2026-01-01", "2026-01-02", "2026-01-03"]
            ),
            "discharge_cusecs": [999, 10, 20, 30],
        }
    )
    result = build_lag_features(df)
    station_a = result[result["station"] == "A"].sort_values("report_datetime")
    # Station A's first (chronologically earliest) reading must have no
    # lag_1 -- NOT station B's 999, even though B's timestamp is earlier.
    assert pd.isna(station_a["lag_1"].iloc[0])


def test_build_lag_features_does_not_mutate_input():
    original = _single_station_df()
    original_copy = original.copy()
    build_lag_features(original)
    pd.testing.assert_frame_equal(original, original_copy)


# ==========================================================
# chronological_split
# ==========================================================

def _ten_row_df():
    return pd.DataFrame(
        {
            "report_datetime": pd.date_range("2026-01-01", periods=10, freq="D"),
            "value": range(10),
        }
    )


def test_chronological_split_no_leakage_and_full_coverage():
    df = _ten_row_df()
    train, val, test = chronological_split(df, train_pct=0.70, val_pct=0.15)

    assert len(train) + len(val) + len(test) == len(df)
    assert not train.empty and not test.empty

    if not val.empty:
        assert train["report_datetime"].max() <= val["report_datetime"].min()
        assert val["report_datetime"].max() <= test["report_datetime"].min()
    else:
        assert train["report_datetime"].max() <= test["report_datetime"].min()


def test_chronological_split_rejects_empty_df():
    with pytest.raises(ValueError):
        chronological_split(pd.DataFrame(columns=["report_datetime", "value"]))


@pytest.mark.parametrize(
    "train_pct,val_pct",
    [(0.0, 0.15), (1.0, 0.0), (0.8, 0.3), (-0.1, 0.15), (0.7, -0.1)],
)
def test_chronological_split_rejects_out_of_range_pcts(train_pct, val_pct):
    df = _ten_row_df()
    with pytest.raises(ValueError):
        chronological_split(df, train_pct=train_pct, val_pct=val_pct)


def test_naive_positional_split_of_unsorted_data_violates_time_ordering():
    """
    Proves the ordering assertions above are not tautological: slicing
    by ROW POSITION on a non-time-sorted DataFrame (the mistake
    chronological_split() exists to prevent) CAN put a later date in
    "train" and an earlier date in "test" -- real leakage. The actual
    chronological_split(), given the exact same shuffled input, does
    not have this problem because it re-sorts by time internally.
    """
    df = _ten_row_df()
    # Deliberately non-time-sorted: day 10 (index 9) placed near the
    # front, day 1 (index 0) placed near the back.
    permuted_positions = [9, 1, 2, 3, 4, 5, 6, 0, 7, 8]
    shuffled = df.iloc[permuted_positions].reset_index(drop=True)

    naive_train = shuffled.iloc[:7]
    naive_test = shuffled.iloc[7:]
    assert naive_train["report_datetime"].max() > naive_test["report_datetime"].min()

    train, val, test = chronological_split(shuffled, train_pct=0.7, val_pct=0.0)
    assert train["report_datetime"].max() <= test["report_datetime"].min()
