from airflow.helpers.script_runner import run_script


def load_ndma():

    run_script(
        "scripts/database/load_ndma.py"
    )


def load_pdma():

    run_script(
        "scripts/database/load_pdma.py"
    )


def load_pmd():

    run_script(
        "scripts/database/load_pmd.py"
    )