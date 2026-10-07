"""
pipeline/dags/ndma_dag.py

National Disaster Management Authority Pipeline

Flow

Extract NDMA
        │
        ▼
Parse NDMA
        │
        ▼
Build Analytics
        │
        ▼
Load PostgreSQL
        │
        ▼
Upload Raw S3
        │
        ▼
Upload Analytics S3

Task 16A (Phase 1 / ADR-0001): AWS Glue and Amazon Redshift were
removed from the project architecture. S3 remains as raw/analytics
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

RAW_FOLDER = PROJECT_ROOT / "data/raw/ndma"

#ANALYTICS_FOLDER = PROJECT_ROOT / "data/analytics/ndma"

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
# EXTRACT NDMA
# ==========================================================

def extract_ndma():

    run_script(

        "scripts/extraction/extract_ndma.py",

        "sitreps",

    )


# ==========================================================
# TASK 2
# PARSE NDMA
# ==========================================================

def parse_ndma():

    run_script(

        "scripts/parsing/parse_ndma.py",

    )


# ==========================================================
# TASK 3
# BUILD ANALYTICS DATASET
# ==========================================================

def build_ndma_dataset():

    run_script(

        "scripts/parsing/build_ndma_dataset.py",

    )


# ==========================================================
# TASK 4
# LOAD POSTGRESQL
# ==========================================================

def load_postgres():

    run_script(

        "scripts/database/load_ndma.py",

    )


# ==========================================================
# TASK 5
# UPLOAD RAW DATA TO AMAZON S3
# ==========================================================

def upload_raw():

    upload_folder(

        str(RAW_FOLDER),

        "raw/ndma",

    )


# ==========================================================
# TASK 6
# UPLOAD ANALYTICS DATA TO AMAZON S3
# ==========================================================

# def upload_analytics():

#     upload_folder(

#         str(ANALYTICS_FOLDER),

#         "analytics/ndma",

#     )


# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="ndma_pipeline",

    description="National Disaster Management Authority Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="0 5 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[

        "Pakistan",

        "NDMA",

        "Disaster",

        "ETL",

        "Airflow",

    ],

) as dag:

    # ======================================================
    # TASKS
    # ======================================================

    extract = PythonOperator(

        task_id="extract_ndma",

        python_callable=extract_ndma,

    )

    parse = PythonOperator(

        task_id="parse_ndma",

        python_callable=parse_ndma,

    )

    analytics = PythonOperator(

        task_id="build_ndma_dataset",

        python_callable=build_ndma_dataset,

    )

    postgres = PythonOperator(

        task_id="load_postgres",

        python_callable=load_postgres,

    )

    raw = PythonOperator(

        task_id="upload_raw_s3",

        python_callable=upload_raw,

    )

    # analytics_upload = PythonOperator(

    #     task_id="upload_analytics_s3",

    #     python_callable=upload_analytics,

    # )

    # ======================================================
    # PIPELINE FLOW
    # ======================================================

    (
        extract
        >> parse
        >> analytics
        >> postgres
        >> raw
    )