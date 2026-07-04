"""
parser_utils.py

Common parser utilities.
"""

import json
from pathlib import Path


def save_json(data: dict, output_file: Path) -> None:
    """
    Save JSON file.
    """

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_file,
        "w",
        encoding="utf8",
    ) as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False,
        )