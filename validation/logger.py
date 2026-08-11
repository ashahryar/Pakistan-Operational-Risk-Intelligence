"""
validation/logger.py
"""

from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "validation.log"


def log_validation(source, status, message):

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    line = (
        f"[{timestamp}] "
        f"{source} | "
        f"{status} | "
        f"{message}\n"
    )

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(line)