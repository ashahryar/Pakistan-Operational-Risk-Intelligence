import subprocess
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_script(script, *args):

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / script),
        *args,
    ]

    process = subprocess.run(

        cmd,

        cwd=str(PROJECT_ROOT),

        capture_output=True,

        text=True,

        env={

            **os.environ,

            "PYTHONPATH": str(PROJECT_ROOT)

        }

    )

    print(process.stdout)

    if process.stderr:
        print(process.stderr)

    if process.returncode != 0:

        raise RuntimeError(

            f"{script} failed."

        )