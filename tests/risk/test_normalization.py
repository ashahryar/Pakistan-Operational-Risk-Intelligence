import pytest

from pipeline.risk.normalization import binary_signal, count_in_window, history_before, min_max, percentile_rank_strict


def test_missing_is_not_zero():
    assert percentile_rank_strict(None, [1, 2, 3], 1) is None
    assert binary_signal(None) is None
    assert min_max(None, 0, 10) is None


def test_zero_remains_zero_and_is_normalized_as_a_real_observation():
    assert percentile_rank_strict(0.0, [0.0, 1.0, 2.0, 3.0], 1) == 0.0   # observed zero rainfall: lowest rank, not "missing"
    assert min_max(0.0, 0.0, 10.0) == 0.0
    assert binary_signal(False) == 0.0


def test_percentile_is_strictly_prior_fraction_below():
    assert percentile_rank_strict(5, [1, 2, 3, 4], 1) == 1.0
    assert percentile_rank_strict(2.5, [1, 2, 3, 4], 1) == 0.5


def test_insufficient_history_returns_none_not_a_guess():
    assert percentile_rank_strict(5, [1, 2], 5) is None
    assert percentile_rank_strict(5, [None, None, 3], 2) is None     # missing prior values do not count as history


def test_history_excludes_the_cell_date_and_all_future_dates():
    series = {"2026-01-01": 1.0, "2026-01-02": 2.0, "2026-01-03": 3.0, "2026-01-04": 99.0}
    assert history_before(series, "2026-01-03") == [1.0, 2.0]


def test_count_in_window_is_date_correct_and_excludes_future():
    dates = ["2026-01-01", "2026-01-10", "2026-01-12", "2026-02-20"]
    assert count_in_window(dates, "2026-01-12", 30) == 3
    assert count_in_window(dates, "2026-01-05", 30) == 1            # 01-10/01-12/02-20 are in the future
    assert count_in_window(dates, "2026-03-01", 30) == 1            # only 02-20 is inside [T-29, T]
    assert count_in_window(dates, "2026-04-15", 30) == 0


def test_min_max_degenerate_range_is_none():
    assert min_max(5, 5, 5) is None
    assert min_max(15, 0, 10) == 1.0
