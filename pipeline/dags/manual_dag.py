"""
pipeline/dags/manual_dag.py

Manual Pipeline

Examples

airflow dags trigger manual_pipeline --conf '{"source":"ndma"}'

airflow dags trigger manual_pipeline --conf '{"source":"pdma"}'

airflow dags trigger manual_pipeline --conf '{"source":"pmd"}'

airflow dags trigger manual_pipeline --conf '{"source":"all"}'
"""

import logging
import os

from pathlib import Path

from datetime import timedelta

from airflow import DAG

from airflow.operators.python import PythonOperator

from airflow.utils.dates import days_ago

from pipeline.helpers.script_runner import run_script

from pipeline.helpers.aws_helper import (

    upload_folder,

    start_glue_job,

)

from pipeline.utils.task_callbacks import (

    task_success,

    task_failure,

)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(

    os.getenv(

        "PROJECT_ROOT",

        "/opt/project",

    )

)

# ==========================================================
# DEFAULT ARGS
# ==========================================================

DEFAULT_ARGS = {

    "owner": "Pakistan Operational Risk Intelligence",

    "depends_on_past": False,

    "retries": 2,

    "retry_delay": timedelta(minutes=5),

    "email_on_failure": False,

    "email_on_retry": False,

    "on_success_callback": task_success,

    "on_failure_callback": task_failure,

}

# ==========================================================
# HELPER
# ==========================================================

def get_source(**context):

    dag_run = context.get("dag_run")

    if dag_run and dag_run.conf:

        return dag_run.conf.get(

            "source",

            "all",

        )

    return "all"

# ==========================================================
# EXTRACT
# ==========================================================

def manual_extract(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("STARTING EXTRACTION")
    logger.info("SOURCE : %s", source)
    logger.info("=" * 80)

    if source in ("ndma", "all"):

        run_script(
            "scripts/extraction/extract_ndma.py",
            "all",
        )

    if source in ("pdma", "all"):

        run_script(
            "scripts/extraction/extract_pdma.py",
            "all",
        )

    if source in ("pmd", "all"):

        run_script(
            "scripts/extraction/extract_pmd.py",
            "all",
        )

    logger.info("Extraction Completed")


# ==========================================================
# PARSE
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

    if source in ("pmd", "all"):

        run_script(
            "scripts/parsing/parse_pmd.py",
        )

    logger.info("Parsing Completed")


# ==========================================================
# LOAD POSTGRES
# ==========================================================

def manual_postgres(**context):

    source = get_source(**context)

    logger.info("=" * 80)
    logger.info("LOADING POSTGRESQL")
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

    logger.info("PostgreSQL Loading Completed")


# ==========================================================
# UPLOAD AMAZON S3
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

    logger.info("S3 Upload Completed")

# ==========================================================
# GLUE
# ==========================================================

# def manual_glue(**context):

#     source = get_source(**context)

#     logger.info("=" * 80)
#     logger.info("STARTING AWS GLUE")
#     logger.info("=" * 80)

#     if source in ("ndma", "all"):

#         start_glue_job(
#             "ndma-glue-job",
#         )

#     if source in ("pdma", "all"):

#         start_glue_job(
#             "pdma-glue-job",
#         )

#     if source in ("pmd", "all"):

#         start_glue_job(
#             "pmd-glue-job",
#         )

#     logger.info("Glue Completed")

# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="manual_pipeline",

    description="Manual ETL Pipeline for NDMA, PDMA and PMD",

    default_args=DEFAULT_ARGS,

    schedule_interval=None,

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[

        "Manual",

        "Pakistan",

        "ETL",

        "Development",

    ],

) as dag:

    # ======================================================
    # TASKS
    # ======================================================

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

    # glue = PythonOperator(

    #     task_id="manual_glue",

    #     python_callable=manual_glue,

    #     execution_timeout=timedelta(minutes=120),

    # )

    # ======================================================
    # PIPELINE FLOW
    # ======================================================

    (
        extract
        >> parse
        >> postgres
        >> s3
        #>> glue
    )