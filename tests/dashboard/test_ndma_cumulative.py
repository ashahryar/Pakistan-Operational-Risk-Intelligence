"""Task 40 -- NDMA figures are cumulative per report; the dashboard must not sum them across reports."""

import numpy as np
import pandas as pd

from dashboard.utils.ndma_cumulative import cumulative_to_increments, peak_totals


def frame(rows):
    return pd.DataFrame(rows, columns=["report_date", "province", "deaths"]).assign(report_date=lambda d: pd.to_datetime(d["report_date"]))


def test_increments_sum_to_the_peak_not_to_the_sum_of_reports():
    df = frame([("2026-07-01", "KP", 0), ("2026-07-02", "KP", 9), ("2026-07-03", "KP", 9), ("2026-07-04", "KP", 12)])
    out = cumulative_to_increments(df, ["deaths"])
    assert out["deaths"].tolist() == [0, 9, 0, 3] and out["deaths"].sum() == 12 == out["deaths_cumulative"].max()
    assert df["deaths"].sum() == 30          # what the dashboard used to show (25 extra deaths)


def test_a_downward_revision_never_creates_negative_or_repeated_counts():
    df = frame([("2026-07-01", "Sindh", 17), ("2026-07-02", "Sindh", 0), ("2026-07-03", "Sindh", 17), ("2026-07-04", "Sindh", 20)])
    out = cumulative_to_increments(df, ["deaths"])
    assert (out["deaths"] >= 0).all() and out["deaths"].sum() == 20


def test_provinces_are_independent_and_missing_values_stay_missing():
    df = frame([("2026-07-01", "KP", 5), ("2026-07-01", "GB", 1), ("2026-07-02", "KP", np.nan), ("2026-07-03", "KP", 8), ("2026-07-03", "GB", 1)])
    out = cumulative_to_increments(df, ["deaths"])
    kp = out[out.province == "KP"]
    assert kp["deaths"].isna().sum() == 1 and kp["deaths"].sum() == 8                  # the NaN day is not turned into 0
    assert out[out.province == "GB"]["deaths"].sum() == 1
    assert peak_totals(df, ["deaths"]) == {"deaths": 9.0}


def test_all_missing_column_has_no_total():
    df = frame([("2026-07-01", "KP", np.nan)])
    assert peak_totals(df, ["deaths"]) == {"deaths": None}
    assert cumulative_to_increments(df, ["deaths"])["deaths"].isna().all()
