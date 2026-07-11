"""
airflow/dags/pdma_dag.py

PDMA Pipeline

Flow

Extract
    ↓
Parse
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


# --------------------------------------------------
# Extraction
# --------------------------------------------------

def extract_pdma():

    for report in (
        "daily",
        "rainfall",
        "gauge",
    ):
        run_script(
            "scripts/extraction/extract_pdma.py",
            report,
        )


# --------------------------------------------------
# Parsing
# --------------------------------------------------

def parse_pdma():

    run_script(
        "scripts/parsing/parse_pdma.py",
    )


# --------------------------------------------------
# PostgreSQL
# --------------------------------------------------

def load_postgres():

    run_script(
        "scripts/database/load_pdma.py",
    )


# --------------------------------------------------
# S3
# --------------------------------------------------

def upload_raw():

    upload_folder(
        "data/raw/pdma",
        "raw/pdma",
    )


def upload_parsed():

    upload_folder(
        "data/parsed/pdma",
        "parsed/pdma",
    )


# --------------------------------------------------
# Glue
# --------------------------------------------------

def glue_job():

    start_glue_job(
        "etl_pdma",
    )


# --------------------------------------------------
# Verification
# --------------------------------------------------

def verify_redshift():

    verify_tables(
        [
            "pdma_daily_reports",
            "pdma_rainfall_readings",
            "pdma_gauge_readings",
        ]
    )


# ==================================================
# DAG
# ==================================================

with DAG(

    dag_id="pdma_pipeline",

    description="PDMA Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="30 5 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[
        "pdma",
        "pakistan",
    ],

) as dag:

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
        task_id="upload_raw",
        python_callable=upload_raw,
    )

    parsed = PythonOperator(
        task_id="upload_parsed",
        python_callable=upload_parsed,
    )

    glue = PythonOperator(
        task_id="glue_etl_pdma",
        python_callable=glue_job,
        execution_timeout=timedelta(minutes=35),
    )

    verify = PythonOperator(
        task_id="verify_redshift",
        python_callable=verify_redshift,
    )

    extract >> parse

    parse >> postgres

    extract >> raw

    parse >> parsed

    parsed >> glue >> verify