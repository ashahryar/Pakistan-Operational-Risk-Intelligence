"""
Project Logger

Common logging utility used across

NDMA
PDMA
PMD
Loaders
Airflow DAGs
Validation
"""

import logging
from pathlib import Path


LOG_DIR = Path("logs")

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_FILE = LOG_DIR / "pipeline.log"


def get_logger(name):

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(

        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    )

    # Console

    console = logging.StreamHandler()

    console.setFormatter(formatter)

    # File

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(console)

    logger.addHandler(file_handler)

    return logger