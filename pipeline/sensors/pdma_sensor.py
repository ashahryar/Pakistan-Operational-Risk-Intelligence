"""
PDMA Sensor

Checks whether new PDMA PDF reports are available.

Current:
    • Compare local downloaded PDFs
    • Store previous scan state

Future:
    • Compare with PDMA website
    • Email / SNS / Slack notifications
"""

from pathlib import Path
from datetime import datetime
import json

RAW_DIR = Path("data/raw/pdma/reports")
STATE_FILE = Path("data/metadata/pdma_last_scan.json")


# ==========================================================
# Helpers
# ==========================================================

def get_existing_files():

    files = set()

    if not RAW_DIR.exists():
        return files

    for pdf in RAW_DIR.rglob("*.pdf"):
        files.add(pdf.name)

    return files


def load_state():

    if not STATE_FILE.exists():
        return {
            "last_scan": None,
            "files": [],
        }

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def save_state(files):

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = {
        "last_scan": datetime.now().isoformat(),
        "total_files": len(files),
        "files": sorted(list(files)),
    }

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
        )


# ==========================================================
# Main Sensor
# ==========================================================

def check_for_new_files():

    print("=" * 60)
    print("PDMA SENSOR")
    print("=" * 60)

    current_files = get_existing_files()

    print(f"Current PDFs : {len(current_files)}")

    state = load_state()

    previous_files = set(state.get("files", []))

    print(f"Previous PDFs: {len(previous_files)}")

    if not previous_files:

        print()
        print("First execution detected.")
        print("Creating baseline...")

        save_state(current_files)

        print("Baseline created successfully.")
        print("=" * 60)

        return False

    new_files = current_files - previous_files
    removed_files = previous_files - current_files

    print()

    if new_files:

        print("NEW FILES FOUND")
        print("-" * 40)

        for file in sorted(new_files):
            print(f"+ {file}")

    else:

        print("No new files found.")

    print()

    if removed_files:

        print("REMOVED FILES")
        print("-" * 40)

        for file in sorted(removed_files):
            print(f"- {file}")

    save_state(current_files)

    print()
    print("=" * 60)
    print(f"Current Files : {len(current_files)}")
    print(f"New Files     : {len(new_files)}")
    print(f"Removed Files : {len(removed_files)}")
    print(f"Last Scan     : {datetime.now().isoformat()}")
    print("=" * 60)

    if new_files:
        return True

    return False


# ==========================================================
# Local Testing
# ==========================================================

if __name__ == "__main__":

    result = check_for_new_files()

    print()
    print(f"Sensor Result : {result}")