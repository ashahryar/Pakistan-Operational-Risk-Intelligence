# Airflow operations (Task 40)

All seven DAGs import cleanly (`airflow dags list-import-errors` is empty; `tests/test_dag_integrity.py` passes in the container). This page states, per DAG, what it ingests and whether it is safe to run on a schedule.

## Operating status

| Status | DAGs |
|---|---|
| **Production, scheduled** | `ndma_pipeline` (daily 05:00 UTC), `pdma_pipeline` (every 6 hours) |
| **Disabled: source unavailable** | `pmd_pipeline` |
| **Manual only** | `weekly_full_pipeline`, `disaster_pipeline`, `manual_pipeline` |
| **Backfill only** | `backfill_pipeline` |

## Per DAG

| | `ndma_pipeline` | `pdma_pipeline` | `pmd_pipeline` |
|---|---|---|---|
| Source | ndma.gov.pk (situation reports, advisories, guidelines) | pdma.punjab.gov.pk (daily, rainfall, gauge, earthquake reports) | nwfc.pmd.gov.pk (daily forecast, weekly outlook), www.pmd.gov.pk (alerts) |
| Extract → raw | `extract_ndma.py` → `data/raw/ndma/reports/*` (PDF + metadata, skips files already downloaded) | `extract_pdma.py` → `data/raw/pdma/reports/*` (same) | `extract_pmd.py` → `data/raw/pmd/reports/*/all/latest.json` (single snapshot, overwritten) |
| Parse → parsed | `parse_ndma.py` → `data/parsed/ndma/sitreps/*.json`; `build_ndma_dataset.py` → `data/analytics/ndma/*.json` | `parse_pdma.py` → `data/parsed/pdma/{daily,rainfall,gauge}/*` | `parse_pmd.py` |
| Load | `load_ndma.py` → `ndma_casualties`, `ndma_damage`, `ndma_rescue`, `ndma_relief` | `load_pdma.py` → `pdma_daily_reports`, `pdma_rainfall_readings`, `pdma_gauge_readings` | `load_pmd.py` → `pmd_daily_forecast`, `pmd_weekly_outlook`, `pmd_weather_alerts` |
| Validation | schema + quality gate per PDF; rejection-ratio gate; rejects to `dq.quarantine` | same pattern | row validation, quarantine |
| Archive | optional S3 step (see below) | optional S3 step (raw and parsed) | optional S3 step |
| Rerun-safe | yes: files are skipped when already downloaded; rows are de-duplicated on `(report_number, report_date, province)` and `ON CONFLICT`; no truncate; quarantine is idempotent | yes: `ON CONFLICT DO NOTHING`, per-row transaction isolation | n/a while disabled |

The other four DAGs reuse the same scripts: `weekly_full_pipeline` (all sources, manual because the two scheduled DAGs already cover NDMA and PDMA and PMD is down), `disaster_pipeline` (master that triggers the three source DAGs), `manual_pipeline` (`--conf '{"source":"ndma|pdma|pmd|all"}'`), `backfill_pipeline` (re-parse existing raw files and reload).

## Source-failure policy (what happens when a site is down)

* An unreachable listing page, a failed download or (PMD) an unfetched report makes the extractor **exit non-zero**. The task goes red, Airflow retries it, and the failure callback fires. Nothing is written for the failed report, so earlier valid data is untouched, and nothing is fabricated.
* "No new reports" is a normal success.
* Before Task 40 the extractors exited 0 in every case, so a dead source looked green (the 4 Oct PMD run recorded `extract_pmd` as *success* while all three PMD pages were failing).
* S3 archiving: `PORI_S3_UPLOAD=off` (default in `.env.docker`) or missing credentials mark the archive task **skipped** with the reason; enabled with credentials that AWS rejects fails fast with a clear message. Skipped is visible in the run; it is not reported as success.
* `quarantine` is idempotent: a scheduled parser re-reads every file, and the same open rejection is no longer inserted again on each run (it had reached 13 rows for one PDF).

## Verification (2026-10-07, real sources)

* **PMD**: `extract_pmd.py all` against the live sites: `nwfc.pmd.gov.pk` daily forecast and weekly outlook answered HTTP 500 and `www.pmd.gov.pk` alerts answered 404 (3 of 3 failed). The extractor now exits 1, the previous `latest.json` (12–14 Aug) was untouched. The DAG stays paused until the URLs are repaired.
* **NDMA**: `ndma_pipeline` ran the full chain against ndma.gov.pk: `extract_ndma` downloaded 14 new PDFs, `parse_ndma` parsed 95 of 99 (the 4 rejects are the files already quarantined), `build_ndma_dataset` and `load_postgres` succeeded, `upload_raw_s3` was **skipped**. The tables grew from 560 to 658 casualty rows (latest report 2026-09-16 → 2026-09-30), 460 → 558 damage rows, 390 → 488 rescue rows, relief 5,117 → 6,117, all visible through the API and dashboard.
* **PDMA**: `pdma_pipeline` ran the full chain against pdma.punjab.gov.pk: `extract_pdma` succeeded (116 s), `parse_pdma` succeeded (1,507 s), `load_postgres` succeeded (66 s), both S3 steps were **skipped**. `pdma_gauge_readings` grew from 16,834 to 18,954 rows (latest report 2026-09-15 → 2026-09-29) and `pdma_daily_reports` from 125 to 138; rainfall had no new reports (869, unchanged). After the manual verification the scheduler continued on its own with scheduled catch-up runs (`ndma_pipeline` 2026-10-06 succeeded).
* **Quarantine**: the table went from 158 to 174 rows during these runs. The original 158 rows are untouched (append-only). Of the 16 added: 7 are transient `[Errno 22] Invalid argument` errors while writing a parsed JSON file on the Windows bind mount (recorded as `unhandled_exception`; the file is re-parsed on the next run), 3 are re-insertions made by parser processes that were already running with the pre-fix writer (which is now idempotent), and 6 are rejections recorded for the first time from newly ingested reports.

## Operating it

```bash
docker exec airflow_webserver airflow dags list                       # all seven, no import errors
docker exec airflow_webserver airflow dags unpause ndma_pipeline      # enable a scheduled DAG
docker exec airflow_webserver airflow dags trigger manual_pipeline --conf '{"source":"ndma"}'
docker exec airflow_postgres psql -U airflow -d airflow -c "select dag_id,is_paused from dag order by 1"
```

The Airflow UI is on `http://localhost:8088`. A DAG that was paused while runs were queued resumes those runs when unpaused: check `dag_run` first (Task 40 found stale queued runs from earlier sessions and marked them failed through Airflow's own models before enabling the DAGs).

## Known gaps

* PMD has no raw history (its `latest.json` is overwritten each run) and its sources are down.
* The Gold build and risk engine are not Airflow tasks: after new ingestion run `scripts/gold/run_gold.py`, `scripts/risk/run_risk_engine.py`, then `scripts/risk/load_risk_serving.py`.
* Retries use the DAG default arguments; there is no alert channel configured beyond the task callbacks.
