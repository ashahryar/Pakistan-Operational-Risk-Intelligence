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
