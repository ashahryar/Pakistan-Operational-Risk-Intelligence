"""
airflow/config/setup_airflow.py

Initialises Airflow for local development.

Run once from the project root:
    python airflow/config/setup_airflow.py
"""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AIRFLOW_HOME = PROJECT_ROOT / "airflow"
DAGS_FOLDER  = AIRFLOW_HOME / "dags"

os.environ["AIRFLOW_HOME"] = str(AIRFLOW_HOME)


def run(cmd: str):
    print(f"\n$ {cmd}")
    result = subprocess.run(
        cmd, shell=True,
        env={**os.environ, "AIRFLOW_HOME": str(AIRFLOW_HOME)},
    )
    if result.returncode != 0:
        print(f"Command failed: {cmd}")
        sys.exit(result.returncode)


def write_airflow_cfg():
    cfg_path = AIRFLOW_HOME / "airflow.cfg"
    if cfg_path.exists():
        print("airflow.cfg already exists — skipping.")
        return

    # Let Airflow generate the default config first
    run("airflow db migrate")

    # Patch dags_folder to point at our dags directory
    text = cfg_path.read_text()
    text = text.replace(
        "dags_folder = ~/airflow/dags",
        f"dags_folder = {DAGS_FOLDER}",
    )
    # Disable example DAGs
    text = text.replace(
        "load_examples = True",
        "load_examples = False",
    )
    cfg_path.write_text(text)
    print(f"Patched airflow.cfg → dags_folder = {DAGS_FOLDER}")


def main():
    print("=" * 60)
    print("AIRFLOW LOCAL SETUP")
    print("=" * 60)
    print(f"AIRFLOW_HOME = {AIRFLOW_HOME}")

    AIRFLOW_HOME.mkdir(parents=True, exist_ok=True)

    # 1. Init / migrate DB
    run("airflow db migrate")

    # 2. Patch config
    write_airflow_cfg()

    # 3. Create admin user (idempotent)
    run(
        "airflow users create "
        "--username admin "
        "--firstname Admin "
        "--lastname User "
        "--role Admin "
        "--email admin@pakistan-risk.local "
        "--password admin123"
    )

    print("\n" + "=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print("\nTo start Airflow locally, open two terminals:\n")
    print("  Terminal 1 (scheduler):")
    print(f"    set AIRFLOW_HOME={AIRFLOW_HOME}")
    print("    airflow scheduler\n")
    print("  Terminal 2 (webserver):")
    print(f"    set AIRFLOW_HOME={AIRFLOW_HOME}")
    print("    airflow webserver --port 8080\n")
    print("  Then open: http://localhost:8080")
    print("  Login: admin / admin123")
    print("=" * 60)


if __name__ == "__main__":
    main()
