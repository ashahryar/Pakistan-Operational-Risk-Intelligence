"""
airflow/dags/ndma_dag.py

NDMA Pipeline

Extract
    ↓
Parse
    ↓
Build Analytics
    ↓
PostgreSQL
    ↓
S3
    ↓
Glue ETL
    ↓
Redshift Verification
"""

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


DEFAULT_ARGS = {
    "owner": "pakistan-risk",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


# -----------------------------
# Extraction
# -----------------------------

def extract_ndma():
    run_script(
        "scripts/extraction/extract_ndma.py",
        "sitreps",
    )


# -----------------------------
# Parsing
# -----------------------------

def parse_ndma():
    run_script(
        "scripts/parsing/parse_ndma.py",
    )


def build_ndma_dataset():
    run_script(
        "scripts/parsing/build_ndma_dataset.py",
    )


# -----------------------------
# PostgreSQL
# -----------------------------

def load_postgres():
    run_script(
        "scripts/database/load_ndma.py",
    )


# -----------------------------
# S3 Upload
# -----------------------------

def upload_raw():
    upload_folder(
        "data/raw/ndma",
        "raw/ndma",
    )


def upload_analytics():
    upload_folder(
        "data/analytics/ndma",
        "analytics/ndma",
    )


# -----------------------------
# Glue
# -----------------------------

def glue_job():
    start_glue_job("etl_ndma")


# -----------------------------
# Verification
# -----------------------------

def verify_redshift():
    verify_tables(
        [
            "ndma_casualties",
            "ndma_damage",
            "ndma_relief",
            "ndma_rescue",
        ]
    )


# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="ndma_pipeline",

    description="NDMA Disaster Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="0 5 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[
        "ndma",
        "pakistan",
    ],

) as dag:

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
        task_id="upload_raw",
        python_callable=upload_raw,
    )

    analytics_upload = PythonOperator(
        task_id="upload_analytics",
        python_callable=upload_analytics,
    )

    glue = PythonOperator(
        task_id="glue_etl_ndma",
        python_callable=glue_job,
        execution_timeout=timedelta(minutes=35),
    )

    verify = PythonOperator(
        task_id="verify_redshift",
        python_callable=verify_redshift,
    )

    extract >> parse >> analytics

    analytics >> postgres

    analytics >> analytics_upload

    extract >> raw

    [raw, analytics_upload] >> glue

    glue >> verify