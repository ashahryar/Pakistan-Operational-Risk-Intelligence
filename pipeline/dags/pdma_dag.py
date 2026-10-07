"""
pipeline/dags/pdma_dag.py

Provincial Disaster Management Authority Pipeline

Flow

Extract PDMA
        │
        ▼
Parse PDMA
        │
        ▼
Load PostgreSQL
        │
        ▼
Upload Raw S3
        │
        ▼
Upload Parsed S3

Task 16A (Phase 1 / ADR-0001): AWS Glue and Amazon Redshift were
removed from the project architecture. S3 remains as raw/parsed
object storage; the analytical/lakehouse platform is now Databricks
(see databricks/README.md), not wired into this DAG.
"""

import os

from pathlib import Path

from datetime import timedelta

from airflow import DAG

from airflow.operators.python import PythonOperator

from airflow.utils.dates import days_ago

from pipeline.helpers.script_runner import run_script

from pipeline.helpers.s3_optional import upload_folder_or_skip as upload_folder

from pipeline.utils.task_callbacks import (

    task_success,

    task_failure,

)

# ==========================================================
# PROJECT
# ==========================================================

PROJECT_ROOT = Path(

    os.getenv(

        "PROJECT_ROOT",

        "/opt/project",

    )

)

# ==========================================================
# PATHS
# ==========================================================

RAW_FOLDER = PROJECT_ROOT / "data/raw/pdma"

PARSED_FOLDER = PROJECT_ROOT / "data/parsed/pdma"

# ==========================================================
# DEFAULT ARGS
# ==========================================================

DEFAULT_ARGS = {

    "owner": "Pakistan Operational Risk Intelligence",

    "depends_on_past": False,

    "retries": 3,

    "retry_delay": timedelta(minutes=5),

    "email_on_failure": False,

    "email_on_retry": False,

    "on_success_callback": task_success,

    "on_failure_callback": task_failure,

}
# ==========================================================
# TASK 1
# EXTRACT PDMA
# ==========================================================

def extract_pdma():

    run_script(

        "scripts/extraction/extract_pdma.py",

        "all",

    )


# ==========================================================
# TASK 2
# PARSE PDMA
# ==========================================================

def parse_pdma():

    run_script(

        "scripts/parsing/parse_pdma.py",

    )


# ==========================================================
# TASK 3
# LOAD POSTGRESQL
# ==========================================================

def load_postgres():

    run_script(

        "scripts/database/load_pdma.py",

    )


# ==========================================================
# TASK 4
# UPLOAD RAW DATA TO AMAZON S3
# ==========================================================

def upload_raw():

    upload_folder(

        str(RAW_FOLDER),

        "raw/pdma",

    )


# ==========================================================
# TASK 5
# UPLOAD PARSED DATA TO AMAZON S3
# ==========================================================

def upload_parsed():

    upload_folder(

        str(PARSED_FOLDER),

        "parsed/pdma",

    )


# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="pdma_pipeline",

    description="Provincial Disaster Management Authority Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="0 */6 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[

        "Pakistan",

        "PDMA",

        "Disaster",

        "ETL",

        "Airflow",

    ],

) as dag:

    # ======================================================
    # TASKS
    # ======================================================

    extract = PythonOperator(

        task_id="extract_pdma",

        python_callable=extract_pdma,

    )

    parse = PythonOperator(

        task_id="parse_pdma",

        python_callable=parse_pdma,

    )

    postgres = PythonOperator(

        task_id="load_postgres",

        python_callable=load_postgres,

    )

    raw = PythonOperator(

        task_id="upload_raw_s3",

        python_callable=upload_raw,

    )

    parsed = PythonOperator(

        task_id="upload_parsed_s3",

        python_callable=upload_parsed,

    )

    # ======================================================
    # PIPELINE FLOW
    # ======================================================

    (
        extract
        >> parse
        >> postgres
        >> raw
        >> parsed
    )