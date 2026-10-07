"""
Weekly Full Pipeline

Runs every Sunday

NDMA
PDMA
PMD

↓

PostgreSQL

↓

Amazon S3

↓

Data Quality Audit

Task 16A (Phase 1 / ADR-0001): AWS Glue and Amazon Redshift were
removed from the project architecture. S3 remains as raw/parsed/
analytics object storage; the analytical/lakehouse platform is now
Databricks (see databricks/README.md), not wired into this DAG.
"""

from datetime import timedelta
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from pipeline.helpers.script_runner import run_script
from pipeline.helpers import s3_optional

logger = logging.getLogger(__name__)

# ==========================================================
# DEFAULT CONFIG
# ==========================================================

DEFAULT_ARGS = {
    "owner": "Pakistan Operational Risk Intelligence",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

# ==========================================================
# EXTRACTION
# ==========================================================


def extract_all():

    logger.info("=" * 70)
    logger.info("STARTING EXTRACTION")
    logger.info("=" * 70)

    # NDMA
    run_script(
        "scripts/extraction/extract_ndma.py",
        "sitreps",
    )

    # PDMA
    for report in (
        "daily",
        "rainfall",
        "gauge",
    ):
        run_script(
            "scripts/extraction/extract_pdma.py",
            report,
        )

    # PMD
    run_script(
        "scripts/extraction/extract_pmd.py",
        "all",
    )

    logger.info("=" * 70)
    logger.info("EXTRACTION COMPLETED")
    logger.info("=" * 70)


# ==========================================================
# PARSING
# ==========================================================


def parse_all():

    logger.info("=" * 70)
    logger.info("STARTING PARSING")
    logger.info("=" * 70)

    run_script("scripts/parsing/parse_ndma.py")

    run_script("scripts/parsing/parse_pdma.py")

    run_script("scripts/parsing/build_ndma_dataset.py")

    logger.info("=" * 70)
    logger.info("PARSING COMPLETED")
    logger.info("=" * 70)


# ==========================================================
# POSTGRES
# ==========================================================


def load_postgres():

    logger.info("=" * 70)
    logger.info("LOADING POSTGRES")
    logger.info("=" * 70)

    run_script("scripts/database/load_ndma.py")

    run_script("scripts/database/load_pdma.py")

    run_script("scripts/database/load_pmd.py")

    logger.info("=" * 70)
    logger.info("POSTGRES COMPLETED")
    logger.info("=" * 70)


# ==========================================================
# S3
# ==========================================================


def upload_all_s3():

    logger.info("=" * 70)
    logger.info("UPLOADING DATA TO AMAZON S3")
    logger.info("=" * 70)

    uploads = [

        ("data/raw/ndma", "raw/ndma"),
        ("data/analytics/ndma", "analytics/ndma"),

        ("data/raw/pdma", "raw/pdma"),
        ("data/parsed/pdma", "parsed/pdma"),

        ("data/raw/pmd", "raw/pmd"),
    ]

    for local_folder, s3_prefix in uploads:

        logger.info(f"Uploading {local_folder}")

        s3_optional.upload_folder_or_skip(
            local_folder,
            s3_prefix,
        )

    logger.info("=" * 70)
    logger.info("ALL S3 UPLOADS COMPLETED")
    logger.info("=" * 70)


# ==========================================================
# DATA QUALITY
# ==========================================================


def audit():

    logger.info("=" * 70)
    logger.info("RUNNING DATA QUALITY AUDIT")
    logger.info("=" * 70)

    run_script(
        "scripts/audit/ndma_data_quality_audit.py"
    )

    logger.info("=" * 70)
    logger.info("AUDIT COMPLETED")
    logger.info("=" * 70)


# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="weekly_full_pipeline",

    description="Weekly Full ETL Pipeline",

    default_args=DEFAULT_ARGS,

    start_date=days_ago(1),

    # Task 40: manual only. It repeats every extraction the three scheduled source DAGs already perform (ndma_pipeline daily, pdma_pipeline every 6 h) and
    # includes PMD, whose source pages are currently unavailable, so a weekly schedule would add a guaranteed failure. Trigger it by hand for a full refresh.
    schedule=None,

    catchup=False,

    max_active_runs=1,

    tags=[
        "weekly",
        "etl",
        "pakistan",
    ],

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

        task_id="load_postgres",

        python_callable=load_postgres,

    )

    s3 = PythonOperator(

        task_id="upload_all_s3",

        python_callable=upload_all_s3,

    )

    # audit_task = PythonOperator(

    #     task_id="data_quality_audit",

    #     python_callable=audit,

    # )

    # Workflow

    extract >> parse

    parse >> postgres

    postgres >> s3

    # s3 >> audit_task