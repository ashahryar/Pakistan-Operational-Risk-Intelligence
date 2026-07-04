"""
metadata.py

Load and save metadata files.
"""

import json
from pathlib import Path


def load_metadata(folder: Path) -> list:

    file = folder / "metadata.json"

    if not file.exists():
        return []

    with open(file, "r", encoding="utf8") as f:
        return json.load(f)


def save_metadata(
    folder: Path,
    metadata: list,
) -> None:

    file = folder / "metadata.json"

    with open(file, "w", encoding="utf8") as f:
        json.dump(
            metadata,
            f,
            indent=4,
            ensure_ascii=False,
        )


def get_downloaded_files(metadata: list) -> set:

    return {
        item["filename"]
        for item in metadata
    }