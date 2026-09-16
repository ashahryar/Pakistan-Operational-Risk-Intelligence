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

Task 16A (Phase 1 / ADR-0001), Part J -- deadlock fix.

This DAG previously ran on its own `0 */6 * * *` schedule (confirmed
by the Task 16 audit, docs/architecture/CODEBASE_AUDIT.md) -- the
EXACT same cron expression `pdma_pipeline` and `pmd_pipeline` already
use for their own, independent, native schedules. Every 6 hours, this
DAG's `TriggerDagRunOperator(reset_dag_run=True, wait_for_completion=True)`
tasks would try to create/reset a run of `pdma_pipeline`/`pmd_pipeline`
at the exact moment those DAGs' own scheduler-created run could also be
starting (both `max_active_runs=1`) -- a real collision/stall risk, not
a hypothetical one, since both schedules fire from the same cron
trigger simultaneously.

Fix: `schedule_interval` is now `None` (manual/on-demand trigger only).
This DAG no longer has ANY independent automatic schedule that could
race against `ndma_pipeline`/`pdma_pipeline`/`pmd_pipeline`'s own
schedules -- there is now exactly one owner of "when does
pdma_pipeline run automatically": `pdma_pipeline` itself (same for
pmd_pipeline, ndma_pipeline). This DAG remains available to manually
trigger a full, sequential, wait-for-each-to-finish run of all three
domains on demand (e.g. a deliberate backfill/verification run), which
is a materially different, much lower-risk scenario than two
independent automatic schedules firing on the same cron tick forever.
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

    # Task 16A deadlock fix (see module docstring): no independent
    # automatic schedule -- manual/on-demand trigger only, so this
    # DAG's TriggerDagRunOperator tasks can never race against
    # pdma_pipeline/pmd_pipeline's own native `0 */6 * * *` schedules.
    schedule_interval=None,

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