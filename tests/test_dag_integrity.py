"""
tests/test_dag_integrity.py

Phase 1 / Task 7 (ADR-0001) — the first automated test in this repository.

Per CLAUDE.md's own gotcha table: "Local package names shadow framework
names -> ~3,400 logged ImportError/NameError. A DagBag import test catches
all of them." This test is that guard.

Must run inside the airflow_webserver / airflow_scheduler container (or
anywhere with the real `airflow` package installed and /opt/airflow/dags
mounted) -- it needs Airflow's own DagBag loader and the real DAGs folder,
neither of which exist on the bare host:

    docker exec -w /opt/project -e PYTHONPATH=/opt/project airflow_webserver \
        pytest tests/test_dag_integrity.py -v

DAGS_FOLDER can be overridden via the DAGS_FOLDER environment variable,
which the fault-injection verification (see Task 7 plan) uses to point
this same test at a scratch copy of the DAGs folder containing a
deliberately broken file, proving the assertions actually fail when they
should -- not just trivially pass.
"""

import os

from airflow.models import DagBag

DAGS_FOLDER = os.environ.get("DAGS_FOLDER", "/opt/airflow/dags")


def _load_dagbag():
    return DagBag(dag_folder=DAGS_FOLDER, include_examples=False)


def test_dagbag_has_no_import_errors():
    dagbag = _load_dagbag()

    assert dagbag.import_errors == {}, (
        f"DagBag reported import errors: {dagbag.import_errors}"
    )


def test_dagbag_found_dags():
    dagbag = _load_dagbag()

    assert len(dagbag.dags) > 0, "DagBag found zero DAGs -- dags folder is empty or misconfigured"


def test_every_dag_has_an_owner():
    dagbag = _load_dagbag()

    missing_owner = [
        dag_id
        for dag_id, dag in dagbag.dags.items()
        if not (dag.default_args or {}).get("owner")
    ]

    assert not missing_owner, f"DAGs with no owner set: {missing_owner}"


def test_every_dag_has_at_least_one_tag():
    dagbag = _load_dagbag()

    missing_tags = [
        dag_id for dag_id, dag in dagbag.dags.items() if not dag.tags
    ]

    assert not missing_tags, f"DAGs with no tags set: {missing_tags}"


def test_no_dag_with_an_automatic_schedule_also_triggers_another_scheduled_dag():
    """
    Phase 1 / Task 16A (ADR-0001), Part J -- static regression guard
    against the exact deadlock/collision class the audit found:
    disaster_pipeline used to run on the SAME `0 */6 * * *` schedule as
    pdma_pipeline/pmd_pipeline while also triggering them via
    TriggerDagRunOperator(reset_dag_run=True, wait_for_completion=True)
    -- two independent owners of "when does this DAG run" racing
    against each other on every matching cron tick.

    Generic check, not hardcoded to disaster_pipeline specifically: for
    every DAG that has its own non-None schedule AND contains a
    TriggerDagRunOperator targeting another DAG, the target DAG must
    NOT also have its own non-None schedule -- exactly one of
    {"the trigger", "the target's own schedule"} may be an active,
    automatic owner of the target DAG's execution.
    """
    from airflow.operators.trigger_dagrun import TriggerDagRunOperator

    dagbag = _load_dagbag()

    violations = []

    for dag_id, dag in dagbag.dags.items():
        triggering_schedule = getattr(dag, "schedule_interval", None)
        if triggering_schedule is None:
            continue  # this DAG has no automatic schedule -- can't race anything

        for task in dag.tasks:
            if isinstance(task, TriggerDagRunOperator):
                target_dag_id = task.trigger_dag_id
                target_dag = dagbag.dags.get(target_dag_id)
                if target_dag is None:
                    continue
                target_schedule = getattr(target_dag, "schedule_interval", None)
                if target_schedule is not None:
                    violations.append(
                        f"{dag_id!r} (schedule={triggering_schedule!r}) triggers "
                        f"{target_dag_id!r} (schedule={target_schedule!r}) via "
                        f"TriggerDagRunOperator -- both have an automatic schedule, "
                        f"a real collision/deadlock risk"
                    )

    assert not violations, "Overlapping schedule ownership found:\n" + "\n".join(violations)


def test_disaster_pipeline_has_no_automatic_schedule():
    """
    Confirms the specific Task 16A fix: disaster_pipeline is
    manual/on-demand trigger only, so it can never race against
    ndma_pipeline/pdma_pipeline/pmd_pipeline's own native schedules.
    """
    dagbag = _load_dagbag()

    dag = dagbag.dags.get("disaster_pipeline")
    assert dag is not None, "disaster_pipeline DAG not found"
    assert getattr(dag, "schedule_interval", "not-none") is None
