"""
logger.py

Shared logging configuration.
"""

import logging
from pathlib import Path


def setup_logger(name: str):

    log_dir = Path("logs")

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    logging.basicConfig(
        filename=log_dir / f"{name}.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    return logging.getLogger(name)