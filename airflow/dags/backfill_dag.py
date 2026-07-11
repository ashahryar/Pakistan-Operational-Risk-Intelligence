"""
airflow/dags/backfill_dag.py

Backfill DAG — manual trigger only (no schedule).

Purpose:
  Re-parse ALL existing raw PDFs and reload everything
  into PostgreSQL, S3, and Redshift from scratch.

  Use this when:
  - Parser logic has been improved
  - Schema has changed
  - Data corruption is detected
  - New historical PDFs have been added manually

Trigger manually from Airflow UI or CLI:
  airflow dags trigger backfill_pipeline
"""

import os
import sys
import time
import subprocess
from datetime import timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_ARGS = {
    "owner":            "pakistan-risk",
    "depends_on_past":  False,
    "retries":          0,
    "email_on_failure": False,
}


def _run(script: str, *args):
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


def reparse_ndma():
    """Re-parse all NDMA PDFs from scratch."""
    _run("scripts/parsing/parse_ndma.py")
    _run("scripts/parsing/build_ndma_dataset.py")


def reparse_pdma():
    """Re-parse all PDMA PDFs from scratch."""
    _run("scripts/parsing/parse_pdma.py")


def reload_postgres():
    """Truncate and reload all PostgreSQL tables."""
    _run("scripts/database/load_ndma.py")
    _run("scripts/database/load_pdma.py")
    _run("scripts/database/load_pmd.py")


def upload_all_s3():
    """Upload all data zones to S3."""
    from aws.s3.upload import upload_all
    upload_all()


def _run_glue(job_name: str):
    import boto3
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    glue = boto3.client(
        "glue",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    run_id = glue.start_job_run(JobName=job_name)["JobRunId"]
    print(f"[Glue] {job_name} RunId={run_id}")
    terminal = {"SUCCEEDED", "FAILED", "ERROR", "TIMEOUT", "STOPPED"}
    for i in range(60):
        time.sleep(30)
        state = glue.get_job_run(JobName=job_name, RunId=run_id)["JobRun"]["JobRunState"]
        print(f"[Glue] {job_name} [{i*30}s] status={state}")
        if state == "SUCCEEDED":
            return
        if state in terminal:
            raise RuntimeError(f"[Glue] {job_name} ended with: {state}")
    raise TimeoutError(f"[Glue] {job_name} timed out")


def reload_redshift():
    """Re-run all Glue ETL jobs to reload Redshift."""
    for job in ("etl_ndma", "etl_pdma", "etl_pmd"):
        _run_glue(job)


def verify_backfill():
    import redshift_connector
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    conn = redshift_connector.connect(
        host=os.getenv("REDSHIFT_HOST"),
        port=int(os.getenv("REDSHIFT_PORT", 5439)),
        database=os.getenv("REDSHIFT_DB", "pakistan_operational_risk"),
        user=os.getenv("REDSHIFT_USER"),
        password=os.getenv("REDSHIFT_PASSWORD"),
    )
    cur = conn.cursor()
    tables = [
        "ndma_casualties", "ndma_damage", "ndma_relief", "ndma_rescue",
        "pmd_reports", "pmd_weather",
        "pdma_daily_reports", "pdma_rainfall_readings", "pdma_gauge_readings",
    ]
    print("\n" + "=" * 55)
    print("BACKFILL VERIFICATION")
    print("=" * 55)
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        print(f"  {t:<35} {n:>8} rows")
    cur.close()
    conn.close()
    print("=" * 55)
    print("Backfill complete.")


with DAG(
    dag_id="backfill_pipeline",
    description="Manual backfill — re-parse all raw data and reload PostgreSQL + S3 + Redshift",
    default_args=DEFAULT_ARGS,
    schedule_interval=None,   # Manual trigger only
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["backfill", "pakistan"],
) as dag:

    t_ndma    = PythonOperator(task_id="reparse_ndma",    python_callable=reparse_ndma)
    t_pdma    = PythonOperator(task_id="reparse_pdma",    python_callable=reparse_pdma)
    t_pg      = PythonOperator(task_id="reload_postgres", python_callable=reload_postgres)
    t_s3      = PythonOperator(task_id="upload_all_s3",   python_callable=upload_all_s3)
    t_rs      = PythonOperator(
        task_id="reload_redshift",
        python_callable=reload_redshift,
        execution_timeout=timedelta(minutes=120),
    )
    t_verify  = PythonOperator(task_id="verify_backfill", python_callable=verify_backfill)

    [t_ndma, t_pdma] >> t_pg >> t_s3 >> t_rs >> t_verify
