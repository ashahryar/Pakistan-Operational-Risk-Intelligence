"""
airflow/dags/manual_dag.py

Manual Pipeline

Examples

airflow dags trigger manual_pipeline --conf '{"source":"ndma"}'
airflow dags trigger manual_pipeline --conf '{"source":"pdma"}'
airflow dags trigger manual_pipeline --conf '{"source":"pmd"}'
airflow dags trigger manual_pipeline --conf '{"source":"all"}'
"""

from datetime import timedelta
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from airflow.helpers.script_runner import run_script
from airflow.helpers.aws_helper import (
    upload_folder,
    start_glue_job,
)

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "pakistan-risk",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
    "email_on_failure": False,
}


# ==========================================================
# Helpers
# ==========================================================

def get_source(**context):

    dag_run = context.get("dag_run")

    if dag_run and dag_run.conf:
        return dag_run.conf.get("source", "all")

    return "all"


# ==========================================================
# Extract
# ==========================================================

def manual_extract(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("STARTING EXTRACTION")
    logger.info("Source : %s", source)
    logger.info("=" * 80)

    if source in ("ndma", "all"):
        run_script(
            "scripts/extraction/extract_ndma.py",
            "sitreps",
        )

    if source in ("pdma", "all"):

        for report in (
            "daily",
            "rainfall",
            "gauge",
        ):

            run_script(
                "scripts/extraction/extract_pdma.py",
                report,
            )

    if source in ("pmd", "all"):

        run_script(
            "scripts/extraction/extract_pmd.py",
            "all",
        )

    logger.info("Extraction completed.")


# ==========================================================
# Parse
# ==========================================================

def manual_parse(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("STARTING PARSING")
    logger.info("=" * 80)

    if source in ("ndma", "all"):

        run_script(
            "scripts/parsing/parse_ndma.py",
        )

        run_script(
            "scripts/parsing/build_ndma_dataset.py",
        )

    if source in ("pdma", "all"):

        run_script(
            "scripts/parsing/parse_pdma.py",
        )

    logger.info("Parsing completed.")


# ==========================================================
# PostgreSQL
# ==========================================================

def manual_postgres(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("LOADING INTO POSTGRESQL")
    logger.info("=" * 80)

    if source in ("ndma", "all"):

        run_script(
            "scripts/database/load_ndma.py",
        )

    if source in ("pdma", "all"):

        run_script(
            "scripts/database/load_pdma.py",
        )

    if source in ("pmd", "all"):

        run_script(
            "scripts/database/load_pmd.py",
        )

    logger.info("PostgreSQL loading completed.")


# ==========================================================
# S3 Upload
# ==========================================================

def manual_s3(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("UPLOADING TO AMAZON S3")
    logger.info("=" * 80)

    if source in ("ndma", "all"):

        upload_folder(
            "data/raw/ndma",
            "raw/ndma",
        )

        upload_folder(
            "data/analytics/ndma",
            "analytics/ndma",
        )

    if source in ("pdma", "all"):

        upload_folder(
            "data/raw/pdma",
            "raw/pdma",
        )

        upload_folder(
            "data/parsed/pdma",
            "parsed/pdma",
        )

    if source in ("pmd", "all"):

        upload_folder(
            "data/raw/pmd",
            "raw/pmd",
        )

    logger.info("S3 upload completed.")


# ==========================================================
# Glue
# ==========================================================

def manual_glue(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("STARTING AWS GLUE JOBS")
    logger.info("=" * 80)

    if source in ("ndma", "all"):

        start_glue_job("etl_ndma")

    if source in ("pdma", "all"):

        start_glue_job("etl_pdma")

    if source in ("pmd", "all"):

        start_glue_job("etl_pmd")

    logger.info("Glue jobs completed.")


# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="manual_pipeline",

    description="Manual Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval=None,

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[
        "manual",
        "pakistan",
    ],

) as dag:

    extract = PythonOperator(
        task_id="manual_extract",
        python_callable=manual_extract,
    )

    parse = PythonOperator(
        task_id="manual_parse",
        python_callable=manual_parse,
    )

    postgres = PythonOperator(
        task_id="manual_postgres",
        python_callable=manual_postgres,
    )

    s3 = PythonOperator(
        task_id="manual_upload_s3",
        python_callable=manual_s3,
    )

    glue = PythonOperator(
        task_id="manual_glue",
        python_callable=manual_glue,
        execution_timeout=timedelta(minutes=120),
    )

    # ======================================================
    # Pipeline Flow
    # ======================================================

    extract >> parse >> postgres >> s3 >> glue