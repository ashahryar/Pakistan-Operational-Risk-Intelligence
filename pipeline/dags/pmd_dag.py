"""
pipeline/dags/pmd_dag.py

Pakistan Meteorological Department Pipeline

Flow

Extract PMD
        │
        ▼
Validate PMD
        │
        ▼
Load PostgreSQL
        │
        ▼
Upload Raw S3
        │
        ▼
Upload Analytics S3
        │
        ▼
Glue ETL
        │
        ▼
Verify Redshift
"""

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

# from pipeline.helpers.redshift_helper import (

#     verify_tables,

# )

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

RAW_FOLDER = PROJECT_ROOT / "data/raw/pmd"

# ANALYTICS_FOLDER = PROJECT_ROOT / "data/analytics/pmd"

# ==========================================================
# AWS
# ==========================================================

# GLUE_JOB = "pmd-glue-job"

# REDSHIFT_TABLES = [

#     "pmd_daily_forecast",

#     "pmd_weekly_outlook",

#     "pmd_weather_alerts",

# ]

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
# EXTRACT PMD
# ==========================================================

def extract_pmd():

    run_script(

        "scripts/extraction/extract_pmd.py",

        "all",

    )


# ==========================================================
# TASK 2
# VALIDATE PMD
# ==========================================================

def validate_pmd():

    run_script(

        "scripts/parsing/parse_pmd.py",

    )


# ==========================================================
# TASK 3
# LOAD POSTGRESQL
# ==========================================================

def load_postgres():

    run_script(

        "scripts/database/load_pmd.py",

    )


# ==========================================================
# TASK 4
# UPLOAD RAW DATA TO AMAZON S3
# ==========================================================

def upload_raw():

    upload_folder(

        str(RAW_FOLDER),

        "raw/pmd",

    )



# ==========================================================
# TASK 6
# START AWS GLUE ETL
# ==========================================================

# def glue_etl():

#     start_glue_job(

#         GLUE_JOB,

#     )


# ==========================================================
# TASK 7
# VERIFY REDSHIFT TABLES
# ==========================================================

# def verify_redshift():

#     verify_tables(

#         REDSHIFT_TABLES,

#     )

# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="pmd_pipeline",

    description="Pakistan Meteorological Department Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="0 */6 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    tags=[

        "Pakistan",

        "PMD",

        "Weather",

        "ETL",

        "Airflow",

    ],

) as dag:

    # ======================================================
    # TASKS
    # ======================================================

    extract = PythonOperator(

        task_id="extract_pmd",

        python_callable=extract_pmd,

    )

    validate = PythonOperator(

        task_id="validate_pmd",

        python_callable=validate_pmd,

    )

    postgres = PythonOperator(

        task_id="load_postgres",

        python_callable=load_postgres,

    )

    raw = PythonOperator(

        task_id="upload_raw_s3",

        python_callable=upload_raw,

    )

    # analytics = PythonOperator(

    #     task_id="upload_analytics_s3",

    #     python_callable=upload_analytics,

    # )

    # glue = PythonOperator(

    #     task_id="glue_etl",

    #     python_callable=glue_etl,

    # )

    # verify = PythonOperator(

    #     task_id="verify_redshift",

    #     python_callable=verify_redshift,

    # )

    # ======================================================
    # PIPELINE FLOW
    # ======================================================

    (
        extract
        >> validate
        >> postgres
        >> raw
#        >> glue
     #   >> verify
    )