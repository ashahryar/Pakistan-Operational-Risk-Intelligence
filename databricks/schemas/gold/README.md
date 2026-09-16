# Gold layer schema contracts

**Status: documented contract, no table implemented.**

Gold tables are the intended eventual source PostgreSQL reads from to
serve the API/dashboard (that sync does not exist yet — see
`databricks/README.md`'s target architecture diagram). Every gold
table is keyed by `admin_unit_id` (from `geo.admin_unit`) and a time
grain (daily, unless noted), so it can join cleanly against the
existing geographic foundation without inventing a second geography
model.

## Example: `gold_district_risk_summary`

| Column | Type | Notes |
|---|---|---|
| `admin_unit_id` | long | FK into `geo.admin_unit` |
| `as_of_date` | date | |
| `flood_risk_score` | double | 0-100, methodology to be defined alongside the first real implementation, not invented here |
| `weather_risk_score` | double | |
| `overall_risk_score` | double | composite, weighting documented alongside the implementation that computes it |
| `contributing_factors` | array<string> | human-readable, e.g. `["gauge level above 80% of danger threshold", "3-day rainfall > 50mm"]` |
| `_computed_at` | timestamp | |
| `_model_version` | string | if ML-derived; NULL if rule-based |

## Example: `gold_ml_features`

The feature table a forecasting model trains against — the gold-layer
successor to `scripts/forecasting/features.py`'s current pandas-based
lag/rolling-window features, once `silver_gauge_observations` exists.
Column contract intentionally left undefined until that silver table
is real; defining feature columns before the silver data they're
computed from exists would be speculative, which Task 16A's own
instructions say to avoid ("do not implement all datasets now").

The remaining planned gold tables (`gold_flood_risk`,
`gold_weather_risk`, `gold_infrastructure_damage`) will have their
column-level contracts documented here as each is actually
implemented.
