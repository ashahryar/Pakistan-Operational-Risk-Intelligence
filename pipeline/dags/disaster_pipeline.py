"""
airflow/dags/disaster_pipeline.py

MASTER DISASTER PIPELINE

Runs complete Pakistan Operational Risk Intelligence Platform

Flow

NDMA
   │
   ▼
PDMA
   │
   ▼
PMD
   │
   ▼
Pipeline Success
"""

from datetime import timedelta

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.dates import days_ago

from pipeline.utils.task_callbacks import (
    dag_success,
    dag_failure,
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

}

# ==========================================================
# DAG
# ==========================================================

with DAG(

    dag_id="disaster_pipeline",

    description="Master Disaster Pipeline",

    default_args=DEFAULT_ARGS,

    schedule_interval="0 */6 * * *",

    start_date=days_ago(1),

    catchup=False,

    max_active_runs=1,

    on_success_callback=dag_success,

    on_failure_callback=dag_failure,

    tags=[

        "Master",

        "Pakistan",

        "Disaster",

        "Airflow",

    ],

) as dag:
    
    # ==========================================================
    # START
    # ==========================================================

    start = EmptyOperator(

        task_id="start_pipeline",

    )

    # ==========================================================
    # NDMA
    # ==========================================================

    ndma = TriggerDagRunOperator(

        task_id="run_ndma_pipeline",

        trigger_dag_id="ndma_pipeline",

        wait_for_completion=True,

        poke_interval=30,

        reset_dag_run=True,

    )

    # ==========================================================
    # PDMA
    # ==========================================================

    pdma = TriggerDagRunOperator(

        task_id="run_pdma_pipeline",

        trigger_dag_id="pdma_pipeline",

        wait_for_completion=True,

        poke_interval=30,

        reset_dag_run=True,

    )

    # ==========================================================
    # PMD
    # ==========================================================

    pmd = TriggerDagRunOperator(

        task_id="run_pmd_pipeline",

        trigger_dag_id="pmd_pipeline",

        wait_for_completion=True,

        poke_interval=30,

        reset_dag_run=True,

    )

    # ==========================================================
    # END
    # ==========================================================

    end = EmptyOperator(

        task_id="pipeline_completed",

    )

    # ==========================================================
    # PIPELINE FLOW
    # ==========================================================

    (

        start
        >> ndma
        >> pdma
        >> pmd
        >> end

    )