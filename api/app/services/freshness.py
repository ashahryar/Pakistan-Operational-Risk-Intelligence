"""Task 41 -- read-only data FRESHNESS per domain, computed from the database at request time (never cached in the API process).

For every domain: the latest date the data itself carries (and which date column that is -- a report date, an observation time and a scrape time
are different things and are never substituted for one another), when a row was last ingested, how many rows exist, and the ingestion / source state.

Source state is only reported when it is supported:
  * ingestion  -- 'scheduled' | 'disabled' from the Airflow DAG's paused flag (Airflow keeps its metadata in this same database); 'unknown' if unreadable.
  * last_run   -- the DAG's latest finished run state, when readable.
  * source_state -- 'unavailable' when the ingestion is disabled because the source is down, or the last run failed; 'available' when the last run
    succeeded; 'unknown' otherwise. The documented reason for a disabled source is carried in `note` (it states when it was last verified).
Nothing here fabricates a date: a domain with no rows reports latest_data_date = null.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from api.app.db import fetch_all

# domain -> (label, table, date expression, date kind, created-at column, DAG that ingests it)
DOMAINS: dict[str, dict[str, Any]] = {
    "ndma": {"label": "NDMA situation reports", "table": "ndma_casualties", "date_sql": "max(report_date)", "date_kind": "report_date",
             "dag": "ndma_pipeline"},
    "pdma_rainfall": {"label": "PDMA rainfall", "table": "pdma_rainfall_readings", "date_sql": "max(report_date)", "date_kind": "report_date",
                      "dag": "pdma_pipeline",
                      "note": "PDMA publishes its 2026 rainfall reports as images; the parser reads PDF reports only, so image reports are not ingested."},
    "pdma_gauge": {"label": "PDMA river gauges", "table": "pdma_gauge_readings", "date_sql": "max(report_datetime)", "date_kind": "observation_datetime",
                   "dag": "pdma_pipeline"},
    "pdma_daily": {"label": "PDMA daily situation reports", "table": "pdma_daily_reports", "date_sql": "max(report_date)", "date_kind": "report_date",
                   "dag": "pdma_pipeline", "note": "Most daily reports carry no parsed report date (the date is not in the parsed document); ingestion time is shown instead."},
    "pmd_weather": {"label": "PMD weather forecast", "table": "pmd_daily_forecast", "date_sql": "max(scraped_at)", "date_kind": "scraped_at",
                    "dag": "pmd_pipeline",
                    "note": "Ingestion is disabled: the PMD sources answered HTTP 500 / 404 when last verified on 2026-10-07 (docs/architecture/AIRFLOW_OPERATIONS.md)."},
}


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def _dag_state(dag_id: str) -> dict:
    """Paused flag and latest finished run of a DAG, from Airflow's metadata tables. Never raises: an unreadable state is 'unknown'."""
    try:
        paused = fetch_all("SELECT is_paused FROM dag WHERE dag_id = :d", {"d": dag_id})
        run = fetch_all("SELECT state, end_date FROM dag_run WHERE dag_id = :d AND state IN ('success', 'failed') ORDER BY end_date DESC NULLS LAST LIMIT 1",
                        {"d": dag_id})
    except Exception:       # HTTPException from fetch_all, or a missing table
        return {"ingestion": "unknown", "last_run_state": None, "last_run_at": None}
    ingestion = "unknown" if not paused else ("disabled" if paused[0]["is_paused"] else "scheduled")
    return {"ingestion": ingestion, "last_run_state": run[0]["state"] if run else None, "last_run_at": _iso(run[0]["end_date"]) if run else None}


def _source_state(ingestion: str, last_run_state: Optional[str]) -> str:
    if ingestion == "disabled":
        return "unavailable"
    if last_run_state == "failed":
        return "unavailable"
    if last_run_state == "success":
        return "available"
    return "unknown"


def _domain_row(key: str, spec: dict) -> dict:
    stats = fetch_all(f"SELECT {spec['date_sql']} AS latest, count(*) AS n, max(created_at) AS ingested FROM {spec['table']}")[0]
    dag = _dag_state(spec["dag"])
    row = {"domain": key, "label": spec["label"], "date_kind": spec["date_kind"], "latest_data_date": _iso(stats["latest"]), "rows": int(stats["n"]),
           "last_ingestion_at": _iso(stats["ingested"]), "dag": spec["dag"], **dag, "source_state": _source_state(dag["ingestion"], dag["last_run_state"]),
           "note": spec.get("note")}
    if key == "pmd_weather" and dag["ingestion"] != "disabled":
        row["note"] = None          # the documented outage applies only while ingestion is disabled
    return row


def _risk_row() -> dict:
    stats = fetch_all("SELECT max(risk_date) AS latest, count(*) AS n, max(loaded_at) AS ingested FROM risk.operational_risk")[0]
    scored = fetch_all("SELECT count(*) AS n FROM risk.latest_operational_risk WHERE risk_score IS NOT NULL")[0]["n"]
    return {"domain": "risk", "label": "Operational risk (engine output)", "date_kind": "risk_date", "latest_data_date": _iso(stats["latest"]),
            "rows": int(stats["n"]), "last_ingestion_at": _iso(stats["ingested"]), "dag": None, "ingestion": "manual", "last_run_state": None, "last_run_at": None,
            "source_state": "not_applicable", "scored_areas": int(scored),
            "note": "Computed by the risk engine, which is run by hand after ingestion (it is not an Airflow task), so it can lag the ingested data."
                    + (" No area has a numeric risk score: scoring is withheld where it is not defensible." if scored == 0 else "")}


def freshness() -> dict:
    domains = [_domain_row(k, s) for k, s in DOMAINS.items()]
    domains.append(_risk_row())
    return {"generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z", "domains": domains}
