"""Task 22 -- authoritative ML feature registry.

One entry per feature actually implemented in pipeline/ml/features.py. No undocumented feature
exists in that module; cross-checked by tests/ml/test_feature_registry.py.

Temporal frequency actually found in the real Gold data (verified before writing this registry,
not assumed -- see docs/architecture/ML_FEATURE_ENGINEERING_STATUS.md for the full inspection):
  - gold_gauge_daily:  genuine daily continuity, ~93 consecutive days, 41 stations -> daily lags
    up to 14 days are defensible.
  - gold_rainfall_daily: 869 observations over only 78 distinct dates across a 16-month span
    (event-driven PDMA reporting, NOT a continuous daily series) -> lag features are defined by
    OBSERVATION ORDER per station, never by calendar-day gaps (a "3-day window" would be
    meaningless when the previous observation for that station may be weeks earlier).
  - gold_weather_daily: all 39 records share ONE calendar date (2026-08-12) -> ZERO temporal
    features are possible; only a same-day availability flag is implemented.
  - gold_air_quality (granularity="daily_district", Lahore only): genuine daily continuity,
    350 consecutive days -> daily lags/rolling windows are defensible, for Lahore only.
    granularity="station_snapshot" (2 records) has no history -> availability flag only.
  - gold_hazard_alerts / gold_disaster_events: event-driven, not a regular series -> "count of
    events with effective time <= T" style features, not lags.

GEOGRAPHY DESIGN DECISION (Task 22 Step 9): gold_gauge_daily is ~97.5% geography-unresolved
(3593/3686 rows, inherited unchanged from Task 20/21 -- not fixed here). Joining rainfall/
weather/AQI/hazard signals into the gauge feature set would require a station -> admin_unit_id
link that does not exist for the overwhelming majority of gauge stations. Rather than fabricate
that link, the gauge model in this task is STATION-LEVEL and AUTOREGRESSIVE ONLY (lags/rolling
statistics of the station's own discharge history + station identity), exactly extending Task 9's
own design. Rainfall/weather/AQI/hazard/disaster features are built and documented as separate,
standalone feature tables (useful once geography resolution improves or for non-gauge targets),
not silently joined into the gauge model.
"""

from __future__ import annotations

from typing import NamedTuple


class FeatureSpec(NamedTuple):
    name: str
    source_dataset: str
    source_field: str
    transformation: str
    time_window: str
    grouping_key: str
    expected_type: str
    leakage_rule: str
    missing_value_behavior: str
    description: str


FEATURE_REGISTRY: dict[str, FeatureSpec] = {
    # ---------------------------------------------------- gauge (primary forecasting target)
    "gauge.lag_1": FeatureSpec(
        "gauge.lag_1", "gold_gauge_daily", "discharge_avg", "shift(1) within station, ordered by date",
        "previous 1 day", "station_name", "float", "uses only the station's own observation strictly "
        "before the target row's date", "NaN if the station has no prior-day observation",
        "previous calendar day's average discharge for this station",
    ),
    "gauge.lag_2": FeatureSpec(
        "gauge.lag_2", "gold_gauge_daily", "discharge_avg", "shift(2)", "previous 2 days", "station_name",
        "float", "strictly historical", "NaN if insufficient history", "discharge 2 days before",
    ),
    "gauge.lag_3": FeatureSpec(
        "gauge.lag_3", "gold_gauge_daily", "discharge_avg", "shift(3)", "previous 3 days", "station_name",
        "float", "strictly historical", "NaN if insufficient history", "discharge 3 days before",
    ),
    "gauge.lag_7": FeatureSpec(
        "gauge.lag_7", "gold_gauge_daily", "discharge_avg", "shift(7)", "previous 7 days", "station_name",
        "float", "strictly historical", "NaN if insufficient history", "discharge 7 days before "
        "(roughly one weekly cycle, defensible given 93 days of history)",
    ),
    "gauge.lag_14": FeatureSpec(
        "gauge.lag_14", "gold_gauge_daily", "discharge_avg", "shift(14)", "previous 14 days", "station_name",
        "float", "strictly historical", "NaN if insufficient history", "discharge 14 days before "
        "(the longest lag still leaving a usable number of rows across the 93-day span)",
    ),
    "gauge.rolling_mean_3": FeatureSpec(
        "gauge.rolling_mean_3", "gold_gauge_daily", "discharge_avg", "shift(1).rolling(3).mean()",
        "3 prior days", "station_name", "float", "window excludes the current row via the shift(1) first",
        "NaN until 3 prior observations exist", "mean discharge over the 3 days before this row",
    ),
    "gauge.rolling_mean_7": FeatureSpec(
        "gauge.rolling_mean_7", "gold_gauge_daily", "discharge_avg", "shift(1).rolling(7).mean()",
        "7 prior days", "station_name", "float", "window excludes the current row", "NaN until "
        "7 prior observations exist", "mean discharge over the 7 days before this row",
    ),
    "gauge.rolling_mean_14": FeatureSpec(
        "gauge.rolling_mean_14", "gold_gauge_daily", "discharge_avg", "shift(1).rolling(14).mean()",
        "14 prior days", "station_name", "float", "window excludes the current row", "NaN until "
        "14 prior observations exist", "mean discharge over the 14 days before this row",
    ),
    "gauge.rolling_min_7": FeatureSpec(
        "gauge.rolling_min_7", "gold_gauge_daily", "discharge_avg", "shift(1).rolling(7).min()",
        "7 prior days", "station_name", "float", "window excludes the current row", "NaN until window full",
        "minimum discharge over the 7 days before this row",
    ),
    "gauge.rolling_max_7": FeatureSpec(
        "gauge.rolling_max_7", "gold_gauge_daily", "discharge_avg", "shift(1).rolling(7).max()",
        "7 prior days", "station_name", "float", "window excludes the current row", "NaN until window full",
        "maximum discharge over the 7 days before this row",
    ),
    "gauge.discharge_change": FeatureSpec(
        "gauge.discharge_change", "gold_gauge_daily", "discharge_avg", "lag_1 - lag_2", "2 prior days",
        "station_name", "float", "built entirely from lag_1/lag_2, both strictly historical",
        "NaN if either lag is NaN", "day-over-day change computed from two PRIOR days (never the "
        "current row's own value)",
    ),
    "gauge.discharge_pct_change": FeatureSpec(
        "gauge.discharge_pct_change", "gold_gauge_daily", "discharge_avg", "(lag_1 - lag_2) / lag_2",
        "2 prior days", "station_name", "float", "built entirely from lag_1/lag_2", "NaN if lag_2 is "
        "NaN or zero", "percentage change computed from two PRIOR days",
    ),
    "gauge.station_resolution_status": FeatureSpec(
        "gauge.station_resolution_status", "gold_gauge_daily", "resolution_status", "pass-through",
        "contemporaneous", "station_name", "category", "not a leakage concern (static per station)",
        "never null -- always one of resolved/ambiguous/unresolved", "whether this station's "
        "geography actually resolved; Task 22 does NOT fabricate a value for unresolved stations "
        "(see module docstring's geography design decision)",
    ),
    "gauge.observation_count": FeatureSpec(
        "gauge.observation_count", "gold_gauge_daily", "observation_count", "pass-through",
        "contemporaneous", "station_name", "int", "static per row, not a leakage concern",
        "never null", "how many raw Silver observations were aggregated into this day's row -- a "
        "data-reliability signal (Step 8)",
    ),
    # ---------------------------------------------------- targets (gauge)
    "gauge.target_t_plus_1": FeatureSpec(
        "gauge.target_t_plus_1", "gold_gauge_daily", "discharge_avg", "shift(-1) within station",
        "next 1 day", "station_name", "float", "a TARGET, never used as an input feature", "NaN for "
        "the final observed day per station (no future row to pull from)",
        "next calendar day's discharge -- the Step 10 primary forecasting target",
    ),
    "gauge.target_t_plus_3": FeatureSpec(
        "gauge.target_t_plus_3", "gold_gauge_daily", "discharge_avg", "shift(-3)", "next 3 days",
        "station_name", "float", "a TARGET, never a feature", "NaN near the series end",
        "discharge 3 days ahead -- computed and reported (persistence baseline only; not modeled "
        "with LinearRegression/RandomForest in this task, see docs)",
    ),
    "gauge.target_t_plus_7": FeatureSpec(
        "gauge.target_t_plus_7", "gold_gauge_daily", "discharge_avg", "shift(-7)", "next 7 days",
        "station_name", "float", "a TARGET, never a feature", "NaN near the series end",
        "discharge 7 days ahead -- persistence baseline only, see docs",
    ),
    # ---------------------------------------------------- rainfall (observation-order, not calendar-day)
    "rainfall.lag_1": FeatureSpec(
        "rainfall.lag_1", "gold_rainfall_daily", "rainfall_total", "shift(1) within station, ordered "
        "by date (OBSERVATION order, not a fixed calendar gap)", "previous 1 observation", "station_name",
        "float", "strictly the prior observation", "stays NaN/None -- a missing rainfall "
        "observation is NEVER treated as 0 mm", "the station's immediately preceding rainfall total",
    ),
    "rainfall.lag_2": FeatureSpec(
        "rainfall.lag_2", "gold_rainfall_daily", "rainfall_total", "shift(2)", "previous 2 observations",
        "station_name", "float", "strictly historical", "NaN, never 0", "2 observations before",
    ),
    "rainfall.lag_3": FeatureSpec(
        "rainfall.lag_3", "gold_rainfall_daily", "rainfall_total", "shift(3)", "previous 3 observations",
        "station_name", "float", "strictly historical", "NaN, never 0", "3 observations before",
    ),
    "rainfall.rolling_sum_3": FeatureSpec(
        "rainfall.rolling_sum_3", "gold_rainfall_daily", "rainfall_total", "shift(1).rolling(3).sum()",
        "previous 3 observations", "station_name", "float", "window excludes current row",
        "NaN until 3 prior observations exist (pandas sum() with min_periods=3, not a silent "
        "zero-fill)", "sum of the 3 most recent PRIOR observations for this station -- NOT a "
        "calendar 3-day total (Step 4: the series is too sparse/irregular to support one)",
    ),
    "rainfall.observation_count": FeatureSpec(
        "rainfall.observation_count", "gold_rainfall_daily", "observation_count", "pass-through",
        "contemporaneous", "station_name", "int", "not a leakage concern", "never null",
        "data-reliability signal",
    ),
    # ---------------------------------------------------- weather (no temporal features possible)
    "weather.single_snapshot_flag": FeatureSpec(
        "weather.single_snapshot_flag", "gold_weather_daily", "date", "constant True",
        "none -- all 39 records share one date (2026-08-12)", "geography_key", "bool", "not applicable "
        "(no history exists to leak)", "always True", "documents that gold_weather_daily currently "
        "has NO temporal depth; no lag/rolling weather feature is implemented because none would be "
        "real (Step 5: 'only use fields actually present')",
    ),
    # ---------------------------------------------------- AQI (daily_district only; Lahore)
    "aqi.lag_1": FeatureSpec(
        "aqi.lag_1", "gold_air_quality", "aqi_avg", "shift(1) within geography_key, filtered to "
        "granularity=='daily_district'", "previous 1 day", "geography_key", "float", "strictly "
        "historical", "NaN if no prior day", "previous day's district AQI (Lahore is currently the "
        "only district with calendar continuity)",
    ),
    "aqi.lag_7": FeatureSpec(
        "aqi.lag_7", "gold_air_quality", "aqi_avg", "shift(7)", "previous 7 days", "geography_key",
        "float", "strictly historical", "NaN if insufficient history", "AQI 7 days before",
    ),
    "aqi.rolling_mean_7": FeatureSpec(
        "aqi.rolling_mean_7", "gold_air_quality", "aqi_avg", "shift(1).rolling(7).mean()", "7 prior days",
        "geography_key", "float", "window excludes current row", "NaN until window full",
        "mean AQI over the 7 days before this row",
    ),
    "aqi.station_snapshot_availability": FeatureSpec(
        "aqi.station_snapshot_availability", "gold_air_quality", "granularity", "count where "
        "granularity=='station_snapshot'", "contemporaneous", "geography_key", "int", "not a leakage "
        "concern (a static count)", "0 if no station-level snapshot exists for that geography",
        "documents that station-level AQI (as opposed to the daily district calendar) has only 2 "
        "records total and supports no lag features (Step 6)",
    ),
    # ---------------------------------------------------- hazard / disaster event features
    "hazard.active_alert_count": FeatureSpec(
        "hazard.active_alert_count", "gold_hazard_alerts", "issued_at/valid_from/valid_until",
        "count of alerts whose validity window covers date T (or, lacking one, whose issued_at <= T)",
        "as-of date T", "admin_unit_id (resolved only)", "int", "only alerts with issued_at <= T are "
        "ever counted -- a future alert can never appear in a T-dated feature", "0 when no alert "
        "is active (a true absence, not a missing measurement -- same documented exception Task 21 "
        "made for count fields)", "how many hazard alerts are in effect for this geography as of T",
    ),
    "hazard.recent_alert_count_7d": FeatureSpec(
        "hazard.recent_alert_count_7d", "gold_hazard_alerts", "issued_at", "count where "
        "T-7 <= issued_at <= T", "7 days", "admin_unit_id (resolved only)", "int", "strictly "
        "issued_at <= T", "0 if none", "alerts issued in the 7 days up to and including T",
    ),
    "disaster.recent_event_count_30d": FeatureSpec(
        "disaster.recent_event_count_30d", "gold_disaster_events", "event_date", "count where "
        "T-30 <= event_date <= T", "30 days", "admin_unit_id (resolved only)", "int", "strictly "
        "event_date <= T", "0 if none", "disaster events reported in the 30 days up to and including T",
    ),
}
