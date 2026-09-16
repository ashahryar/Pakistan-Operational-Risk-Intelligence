"""
airflow/dags/backfill_dag.py

MASTER BACKFILL PIPELINE

Purpose

Rebuild complete platform from existing historical data.

Flow

NDMA Reparse
      │
      ▼
PDMA Reparse
      │
      ▼
PMD Parse
      │
      ▼
Reload PostgreSQL
      │
      ▼
Upload S3

Task 16A (Phase 1 / ADR-0001): AWS Glue and Amazon Redshift were
removed from the project architecture. S3 remains as raw/analytics
object storage; the analytical/lakehouse platform is now Databricks
(see databricks/README.md), not wired into this DAG.
"""

import os
import sys
import subprocess

from pathlib import Path
from datetime import timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from pipeline.utils.task_callbacks import (
    task_success,
    task_failure,
    dag_success,
    dag_failure,
)

from pipeline.helpers.aws_helper import (
    upload_all,
)

# ==========================================================
# PROJECT
# ==========================================================

PROJECT_ROOT = Path(
    os.getenv("PROJECT_ROOT", "/opt/project")
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ==========================================================
# CONFIG
# ==========================================================

# ==========================================================
# DEFAULT ARGS
# ==========================================================

DEFAULT_ARGS = {

    "owner": "Pakistan Operational Risk Intelligence",

    "depends_on_past": False,

    "retries": 1,

    "retry_delay": timedelta(minutes=5),

    "email_on_failure": False,

    "email_on_retry": False,

    "on_success_callback": task_success,

    "on_failure_callback": task_failure,

}

# ==========================================================
# SCRIPT RUNNER
# ==========================================================

def run(script, *args):

    cmd = [

        sys.executable,

        str(PROJECT_ROOT / script),

        *args,

    ]

    process = subprocess.run(

        cmd,

        cwd=str(PROJECT_ROOT),

        capture_output=True,

        text=True,

        env={

            **os.environ,

            "PYTHONPATH": str(PROJECT_ROOT),

        },

    )

    if process.stdout:
        print(process.stdout)

    if process.stderr:
        print(process.stderr)

    if process.returncode != 0:

        raise RuntimeError(

            f"{script} failed."

        )
    
# ==========================================================
# NDMA
# ==========================================================

def reparse_ndma():

    run(
        "scripts/parsing/parse_ndma.py",
    )

    run(
        "scripts/parsing/build_ndma_dataset.py",
    )


# ==========================================================
# PDMA
# ==========================================================

def reparse_pdma():

    run(
        "scripts/parsing/parse_pdma.py",
    )


# ==========================================================
# PMD
# ==========================================================

def parse_pmd():

    run(
        "scripts/parsing/parse_pmd.py",
    )


# ==========================================================
# POSTGRES
# ==========================================================

def reload_postgres():

    run(
        "scripts/database/load_ndma.py",
    )

    run(
        "scripts/database/load_pdma.py",
    )

    run(
        "scripts/database/load_pmd.py",
    )


# ==========================================================
# S3
# ==========================================================

def upload_all_s3():

    upload_all()


# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="backfill_pipeline",

    description="Complete Platform Backfill Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval=None,

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    on_success_callback=dag_success,

    on_failure_callback=dag_failure,

    tags=[
        "backfill",
        "pakistan",
        "etl",
    ],

) as dag:

    # ======================================================
    # TASKS
    # ======================================================

    ndma = PythonOperator(

        task_id="reparse_ndma",

        python_callable=reparse_ndma,

    )

    pdma = PythonOperator(

        task_id="reparse_pdma",

        python_callable=reparse_pdma,

    )

    pmd = PythonOperator(

        task_id="parse_pmd",

        python_callable=parse_pmd,

    )

    postgres = PythonOperator(

        task_id="reload_postgres",

        python_callable=reload_postgres,

    )

    s3 = PythonOperator(

        task_id="upload_all_s3",

        python_callable=upload_all,

    )

    # ======================================================
    # PIPELINE
    # ======================================================

    [ndma, pdma, pmd] >> postgres

    postgres >> s3