"""
airflow/dags/pmd_dag.py

PMD Pipeline

Flow

Extract
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

def extract_pmd():

    run_script(
        "scripts/extraction/extract_pmd.py",
        "all",
    )


# --------------------------------------------------
# PostgreSQL
# --------------------------------------------------

def load_postgres():

    run_script(
        "scripts/database/load_pmd.py",
    )


# --------------------------------------------------
# S3
# --------------------------------------------------

def upload_raw():

    upload_folder(
        "data/raw/pmd",
        "raw/pmd",
    )


# --------------------------------------------------
# Glue
# --------------------------------------------------

def glue_job():

    start_glue_job(
        "etl_pmd",
    )


# --------------------------------------------------
# Verification
# --------------------------------------------------

def verify_redshift():

    verify_tables(
        [
            "pmd_reports",
            "pmd_weather",
            "pmd_weekly_outlook",
        ]
    )


# ==================================================
# DAG
# ==================================================

with DAG(

    dag_id="pmd_pipeline",

    description="PMD Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="0 6 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[
        "pmd",
        "pakistan",
    ],

) as dag:

    extract = PythonOperator(
        task_id="extract_pmd",
        python_callable=extract_pmd,
    )

    postgres = PythonOperator(
        task_id="load_postgres",
        python_callable=load_postgres,
    )

    raw = PythonOperator(
        task_id="upload_raw",
        python_callable=upload_raw,
    )

    glue = PythonOperator(
        task_id="glue_etl_pmd",
        python_callable=glue_job,
        execution_timeout=timedelta(minutes=35),
    )

    verify = PythonOperator(
        task_id="verify_redshift",
        python_callable=verify_redshift,
    )

    extract >> [postgres, raw]

    raw >> glue >> verify