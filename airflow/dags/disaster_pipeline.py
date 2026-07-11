"""
airflow/dags/disaster_pipeline.py

Pakistan Operational Risk Intelligence — Full Pipeline DAG
Runs daily at 06:00 PKT (01:00 UTC)

DATA FLOW
─────────────────────────────────────────────────────────────
  WEBSITES
      │
      ▼
  STAGE 1 — EXTRACT  (scrape PDFs + JSON from NDMA/PDMA/PMD)
      │
      ▼
  STAGE 2 — PARSE    (PDF → structured JSON, build analytics)
      │
      ├──► STAGE 3 — LOAD POSTGRESQL  (local DB for Streamlit)
      │
      └──► STAGE 4 — UPLOAD S3
               data/raw       → s3://bucket/raw/
               data/parsed    → s3://bucket/parsed/
               data/analytics → s3://bucket/analytics/
                    │
                    ▼
             STAGE 5 — AWS GLUE  (S3 → Redshift Serverless)
                    │
                    ▼
             STAGE 6 — VERIFY REDSHIFT  (row-count checks)
─────────────────────────────────────────────────────────────
"""
import os
import sys
import time
import subprocess
from pathlib import Path

from datetime import timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from airflow.helpers.script_runner import run_script
from airflow.helpers.aws_helper import (
    upload_folder,
    start_glue_job,
)
from airflow.helpers.redshift_helper import verify_tables

# ── project root ──────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# ── default args ──────────────────────────────────────────
DEFAULT_ARGS = {
    "owner":            "pakistan-risk",
    "depends_on_past":  False,
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}


# ══════════════════════════════════════════════════════════
# HELPER — run a local script as subprocess
# ══════════════════════════════════════════════════════════

def _run(script: str, *args):
    """
    Run  python <PROJECT_ROOT>/<script> [args]  from PROJECT_ROOT.
    Raises RuntimeError on non-zero exit.
    """
    cmd = [sys.executable, str(PROJECT_ROOT / script)] + list(args)
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError(f"{script} exited with code {proc.returncode}")


# ══════════════════════════════════════════════════════════
# STAGE 1 — EXTRACT
# Scrape raw PDFs and JSON from government websites
# ══════════════════════════════════════════════════════════
def extract_ndma():
    run_script(
        "scripts/extraction/extract_ndma.py",
        "sitreps",
    )


def extract_pdma():
    for report in ("daily", "rainfall", "gauge"):
        run_script(
            "scripts/extraction/extract_pdma.py",
            report,
        )


def extract_pmd():
    run_script(
        "scripts/extraction/extract_pmd.py",
        "all",
    )

# ══════════════════════════════════════════════════════════
# STAGE 2 — PARSE
# Convert raw PDFs → structured JSON
# ══════════════════════════════════════════════════════════

def parse_ndma():
    run_script("scripts/parsing/parse_ndma.py")


def parse_pdma():
    run_script("scripts/parsing/parse_pdma.py")


def build_ndma_dataset():
    run_script("scripts/parsing/build_ndma_dataset.py")
# ══════════════════════════════════════════════════════════
# STAGE 3 — LOAD POSTGRESQL  (local, feeds Streamlit)
# ══════════════════════════════════════════════════════════

def load_pg_ndma():
    run_script("scripts/database/load_ndma.py")


def load_pg_pdma():
    run_script("scripts/database/load_pdma.py")


def load_pg_pmd():
    run_script("scripts/database/load_pmd.py")

# ══════════════════════════════════════════════════════════
# STAGE 4 — UPLOAD TO S3
# Push all local data to S3 so Glue can read it
# ══════════════════════════════════════════════════════════

def upload_raw():

    upload_folder(
        "data/raw",
        "raw",
    )


def upload_parsed():

    upload_folder(
        "data/parsed",
        "parsed",
    )


def upload_analytics():

    upload_folder(
        "data/analytics",
        "analytics",
    )

# ══════════════════════════════════════════════════════════
# STAGE 5 — AWS GLUE  (S3 → Redshift Serverless)
# Triggered via boto3 from local Airflow, runs in AWS cloud
# ══════════════════════════════════════════════════════════

def glue_ndma():

    start_glue_job("etl_ndma")


def glue_pdma():

    start_glue_job("etl_pdma")


def glue_pmd():

    start_glue_job("etl_pmd")

# ══════════════════════════════════════════════════════════
# STAGE 6 — VERIFY REDSHIFT
# Row-count sanity check after Glue loads
# ══════════════════════════════════════════════════════════

def verify_redshift():

    verify_tables(
        [
            "ndma_casualties",
            "ndma_damage",
            "ndma_relief",
            "ndma_rescue",

            "pdma_daily_reports",
            "pdma_rainfall_readings",
            "pdma_gauge_readings",

            "pmd_reports",
            "pmd_weather",
            "pmd_weekly_outlook",
        ]
    )

# ══════════════════════════════════════════════════════════
# DAG
# ══════════════════════════════════════════════════════════

with DAG(
    dag_id="pakistan_disaster_pipeline",
    description="Pakistan Operational Risk — Extract → Parse → PostgreSQL → S3 → Glue → Redshift",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 1 * * *",   # 01:00 UTC = 06:00 PKT
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["pakistan", "ndma", "pdma", "pmd", "aws"],
) as dag:

    # ── Stage 1 ───────────────────────────────────────────
    t_ext_ndma = PythonOperator(task_id="extract_ndma", python_callable=extract_ndma)
    t_ext_pdma = PythonOperator(task_id="extract_pdma", python_callable=extract_pdma)
    t_ext_pmd  = PythonOperator(task_id="extract_pmd",  python_callable=extract_pmd)

    # ── Stage 2 ───────────────────────────────────────────
    t_parse_ndma   = PythonOperator(task_id="parse_ndma",         python_callable=parse_ndma)
    t_parse_pdma   = PythonOperator(task_id="parse_pdma",         python_callable=parse_pdma)
    t_build_ndma   = PythonOperator(task_id="build_ndma_dataset", python_callable=build_ndma_dataset)

    # ── Stage 3 ───────────────────────────────────────────
    t_pg_ndma = PythonOperator(task_id="load_pg_ndma", python_callable=load_pg_ndma)
    t_pg_pdma = PythonOperator(task_id="load_pg_pdma", python_callable=load_pg_pdma)
    t_pg_pmd  = PythonOperator(task_id="load_pg_pmd",  python_callable=load_pg_pmd)

    # ── Stage 4 ───────────────────────────────────────────
    t_s3_raw       = PythonOperator(task_id="upload_s3_raw",       python_callable=upload_raw)
    t_s3_parsed    = PythonOperator(task_id="upload_s3_parsed",    python_callable=upload_parsed)
    t_s3_analytics = PythonOperator(task_id="upload_s3_analytics", python_callable=upload_analytics)

    # ── Stage 5 ───────────────────────────────────────────
    t_glue_ndma = PythonOperator(
        task_id="glue_etl_ndma", python_callable=glue_ndma,
        execution_timeout=timedelta(minutes=35),
    )
    t_glue_pdma = PythonOperator(
        task_id="glue_etl_pdma", python_callable=glue_pdma,
        execution_timeout=timedelta(minutes=35),
    )
    t_glue_pmd = PythonOperator(
        task_id="glue_etl_pmd",  python_callable=glue_pmd,
        execution_timeout=timedelta(minutes=35),
    )

    # ── Stage 6 ───────────────────────────────────────────
    t_verify = PythonOperator(task_id="verify_redshift", python_callable=verify_redshift)

    # ══════════════════════════════════════════════════════
    # DEPENDENCY GRAPH
    #
    #  extract_ndma ──► parse_ndma ──► build_ndma_dataset ──► load_pg_ndma
    #                                       │
    #                                       └──► upload_s3_analytics ──► glue_etl_ndma ──┐
    #                                                                                      │
    #  extract_pdma ──► parse_pdma ──► load_pg_pdma                                       ├──► verify_redshift
    #                       │                                                              │
    #                       └──────────► upload_s3_parsed ──────────────► glue_etl_pdma ──┤
    #                                                                                      │
    #  extract_pmd ──► load_pg_pmd                                                         │
    #       │                                                                              │
    #       └──────────────────────────► upload_s3_raw ──────────────────► glue_etl_pmd ──┘
    #
    # extract_ndma ──┐
    # extract_pdma ──┼──► upload_s3_raw   (all raw data in one task)
    # extract_pmd  ──┘
    # ══════════════════════════════════════════════════════

    # Stage 1 → Stage 2
    t_ext_ndma >> t_parse_ndma >> t_build_ndma
    t_ext_pdma >> t_parse_pdma
    t_ext_pmd  >> t_pg_pmd

    # Stage 2 → Stage 3 (PostgreSQL)
    t_build_ndma >> t_pg_ndma
    t_parse_pdma >> t_pg_pdma

    # Stage 2 → Stage 4 (S3 uploads)
    # raw: wait for all extracts to finish before uploading
    [t_ext_ndma, t_ext_pdma, t_ext_pmd] >> t_s3_raw

    # parsed: wait for both parse jobs
    [t_parse_ndma, t_parse_pdma] >> t_s3_parsed

    # analytics: wait for ndma dataset build
    t_build_ndma >> t_s3_analytics

    # Stage 4 → Stage 5 (Glue reads from S3)
    t_s3_analytics >> t_glue_ndma   # analytics/ndma/ → Redshift ndma_*
    t_s3_parsed    >> t_glue_pdma   # parsed/pdma/    → Redshift pdma_*
    t_s3_raw       >> t_glue_pmd    # raw/pmd/        → Redshift pmd_*

    # Stage 5 → Stage 6
    [t_glue_ndma, t_glue_pdma, t_glue_pmd] >> t_verify
