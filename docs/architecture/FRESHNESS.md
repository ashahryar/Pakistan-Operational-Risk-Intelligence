# Data freshness and dashboard caching (Task 41)

## Where freshness was lost (diagnosed on 2026-10-07, before any code change)

| Domain | Source (newest) | Parsed | PostgreSQL | API (before) | Dashboard (before) | Where it was lost |
|---|---|---|---|---|---|---|
| NDMA | report titled 30 Sep 2026 (source metadata) | 96 JSON files | 2026-09-30 | 2026-09-30 | 2026-09-30 | **Not lost.** NDMA has published nothing newer. |
| PDMA rainfall | PDFs to 2026-07-15; **103 image reports to 2026-10-07** | PDFs only, to 2026-07-15 | 2026-07-14 | 2026-07-14 | 2026-07-14 | The 2026 reports are published as `.jpeg`; the parser reads PDFs only, so they are downloaded and never ingested. Nothing was shown about this. |
| PDMA gauges | 2026-10-07 | 2026-10-07 | 2026-10-07 12:00 | **2026-09-15** | **2026-09-15** | `/api/v1/evidence/gauge-stations` served a committed evidence snapshot held in an `lru_cache` for the life of the API process; the Rivers page showed that frozen range. |
| PMD weather | sources answer HTTP 500 / 404 | 2026-08-12 | 2026-08-12 | 2026-08-12 | 2026-08-12 | **Not a dashboard fault.** The source is down; the page did not say so. |
| Risk | derived | n/a | 2026-09-16 | 2026-09-16 | 2026-09-16 | The risk engine is run by hand after ingestion, so it lags the ingested data (21 days here). |

The dashboard's own caches were not the cause of any stale date: `dashboard/db.py` caches for 60 seconds.

## The cache crash

`@st.cache_data` pickles what a function returns. The cached helpers returned `dashboard.api_client.ApiResult`, a dataclass; pickle stores it by reference to that module's class, so once a long-running server replaced the module (Streamlit purges changed modules) the old instance no longer matched the class and Streamlit raised `UnserializableReturnValueError` (Home `_risk_latest`, Rivers `_evidence`, Risk Map `_provinces`; the same pattern existed in every other API helper).

**Fix (`dashboard/utils/api_cache.py`).** `@cached_api(ttl)` caches only a plain dict (`ok, data, error_kind, message, status_code, fetched_at`) and rebuilds the `ApiResult` on the way out. A failed call is raised inside the cached function, so Streamlit never stores it: the next run retries, and the caller still sees the same kind, message, status and body. Cache keys include the function name (Streamlit ignores underscore-prefixed arguments, which would have let two functions share an entry). The admin-unit helpers in the Operational Intelligence sections used to cache an empty list when the API was down; they now go through the same boundary.

## Freshness architecture

* **API `GET /api/v1/freshness`** (read-only, computed per request, never cached): per domain the latest date the data carries *and which date column it is* (`report_date`, `observation_datetime`, `scraped_at`, `risk_date` are never substituted for one another), the last row ingested, the row count, the ingesting DAG's state (`scheduled` / `disabled`, last run) and a source state (`available`, `unavailable`, `unknown`). `unavailable` means ingestion is disabled or the last run failed; for PMD the documented outage is carried in `note`.
* **Gauge evidence** now merges live per-station observation days and dates from `pdma_gauge_readings` into the committed geography evidence (the geography states are untouched). If the database is unreadable the snapshot is served and `summary.observations_source` says `evidence_snapshot`.
* **`dashboard/utils/freshness.py`**: one pure `describe()` (clock injected) producing `current`, `stale`, `source_unavailable`, `no_data` or `unknown`, with only the fields the API supplied ("Latest available", "Last successful ingestion", "Source status"). Pages call `render_freshness(domain)`; Home's coverage table uses the same rows.
* Stale thresholds (presentation only): NDMA 7 days, rainfall 7, gauges 2, daily reports 3, PMD 2, risk 7.

## Refresh behaviour

Database reads are cached for 60 s, API reads for 60-300 s, and `render_refresh_control()` adds a **Refresh data** button to every data page that clears every cache and reruns. After ingestion a normal reload (or the button) shows the new data; no Python restart is needed. The Weather and Rainfall pages also keep their existing 60 s auto-refresh when `streamlit-autorefresh` is installed. A server that is running *old code* still needs a restart after a code change (it keeps imported modules), which is unrelated to data refresh.

## Known limits

* PDMA rainfall after 2026-07-15 exists only as images and is not ingested (no OCR was added).
* Risk is computed by hand (`scripts/gold/run_gold.py`, `scripts/risk/run_risk_engine.py`, `scripts/risk/load_risk_serving.py`); the dashboard reports its age instead of hiding it.
* The Airflow-derived source state needs the Airflow metadata tables in the same database (the current deployment); otherwise it is `unknown`.
* `ndma_casualties.injured` is NULL on 77 rows and the NDMA casualty page converts NULL to 0 in its own charts (pre-existing; the Home totals ignore NULLs).
