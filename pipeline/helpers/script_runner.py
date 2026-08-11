import os
import sys
import time
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_script(script: str, *args):
    """
    Execute a Python script from the project root.

    Parameters
    ----------
    script : str
        Relative path to python script.
    args : tuple
        Optional command-line arguments.

    Returns
    -------
    str
        Script stdout.
    """

    script_path = PROJECT_ROOT / script

    print("=" * 70)
    print(f"Running : {script}")
    print("=" * 70)

    start = time.time()

    cmd = [
        sys.executable,
        str(script_path),
        *args,
    ]

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT),
        },
    )

    elapsed = round(time.time() - start, 2)

    if result.stdout.strip():
        print(result.stdout)

    if result.stderr.strip():
        print(result.stderr)

    if result.returncode != 0:

        raise RuntimeError(
            f"""
Script Failed

Script : {script}

Exit Code : {result.returncode}

Time : {elapsed} sec
"""
        )

    print("-" * 70)
    print(f"Completed : {script}")
    print(f"Execution Time : {elapsed} sec")
    print("-" * 70)

    return result.stdout