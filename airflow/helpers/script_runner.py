import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_script(script: str, *args):
    """
    Execute any local python script.
    """

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / script),
        *args
    ]

    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT)
        }
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"{script} failed ({result.returncode})"
        )