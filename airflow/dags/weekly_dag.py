"""
airflow/dags/weekly_dag.py

Weekly Full Pipeline

Runs every Sunday

NDMA + PDMA + PMD
→ PostgreSQL
→ S3
→ Glue
→ Redshift
→ Data Quality Audit
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
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}


# =========================================================
# Extraction
# =========================================================

def extract_all():

    run_script("scripts/extraction/extract_ndma.py", "sitreps")

    for report in ("daily", "rainfall", "gauge"):
        run_script("scripts/extraction/extract_pdma.py", report)

    run_script("scripts/extraction/extract_pmd.py", "all")


# =========================================================
# Parsing
# =========================================================

def parse_all():

    run_script("scripts/parsing/parse_ndma.py")
    run_script("scripts/parsing/parse_pdma.py")
    run_script("scripts/parsing/build_ndma_dataset.py")


# =========================================================
# PostgreSQL
# =========================================================

def load_all_postgres():

    run_script("scripts/database/load_ndma.py")
    run_script("scripts/database/load_pdma.py")
    run_script("scripts/database/load_pmd.py")


# =========================================================
# Upload to S3
# =========================================================

def upload_all_s3():

    upload_folder("data/raw/ndma", "raw/ndma")
    upload_folder("data/analytics/ndma", "analytics/ndma")

    upload_folder("data/raw/pdma", "raw/pdma")
    upload_folder("data/parsed/pdma", "parsed/pdma")

    upload_folder("data/raw/pmd", "raw/pmd")


# =========================================================
# Glue
# =========================================================

def glue_all():

    start_glue_job("etl_ndma")
    start_glue_job("etl_pdma")
    start_glue_job("etl_pmd")


# =========================================================
# Data Quality
# =========================================================

def data_quality_audit():

    run_script("scripts/audit/ndma_data_quality_audit.py")


# =========================================================
# Verify Redshift
# =========================================================

def verify_all_redshift():

    verify_tables([
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
    ])


# =========================================================
# DAG
# =========================================================

with DAG(
    dag_id="weekly_full_pipeline",
    description="Weekly Full Refresh Pipeline",
    default_args=DEFAULT_ARGS,
    schedule="0 4 * * 0",
    start_date=days_ago(7),
    catchup=False,
    max_active_runs=1,
    tags=["weekly", "pakistan"],
) as dag:

    extract = PythonOperator(
        task_id="extract_all",
        python_callable=extract_all,
    )

    parse = PythonOperator(
        task_id="parse_all",
        python_callable=parse_all,
    )

    postgres = PythonOperator(
        task_id="load_all_postgres",
        python_callable=load_all_postgres,
    )

    s3 = PythonOperator(
        task_id="upload_all_s3",
        python_callable=upload_all_s3,
    )

    glue = PythonOperator(
        task_id="glue_all_etl",
        python_callable=glue_all,
        execution_timeout=timedelta(minutes=120),
    )

    audit = PythonOperator(
        task_id="data_quality_audit",
        python_callable=data_quality_audit,
    )

    verify = PythonOperator(
        task_id="verify_all_redshift",
        python_callable=verify_all_redshift,
    )

    extract >> parse
    parse >> postgres
    parse >> s3
    postgres >> audit
    s3 >> glue >> verify