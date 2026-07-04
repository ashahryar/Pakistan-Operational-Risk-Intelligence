from pathlib import Path
import json

from common.parser_utils import save_json

INPUT_FOLDER = Path("data/parsed/ndma/sitreps")
OUTPUT_FOLDER = Path("data/analytics/ndma")

OUTPUT_FOLDER.mkdir(
    parents=True,
    exist_ok=True,
)

provinces = [
    "Punjab",
    "KP",
    "Sindh",
    "Balochistan",
    "GB",
    "AJK",
    "ICT",
]

casualties = []
damage = []
relief = []
rescue = []

for file in INPUT_FOLDER.glob("*.json"):

    with open(file, encoding="utf8") as f:
        report = json.load(f)

    report_date = report["report_date"]
    report_number = report["report_number"]

    # -----------------------
    # Casualties
    # -----------------------

    for row in report["casualties"]:

        row["report_date"] = report_date
        row["report_number"] = report_number

        casualties.append(row)

    # -----------------------
    # Damage
    # -----------------------

    for row in report["damage"]:

        row["report_date"] = report_date
        row["report_number"] = report_number

        damage.append(row)

    # -----------------------
    # Relief
    # -----------------------

    for row in report["relief"]:

        if len(row) < len(provinces) + 1:
            continue

        item = str(row[0]).strip()

        for i, province in enumerate(provinces):

            quantity = str(row[i + 1]).strip()

            # Skip invalid or zero values
            if quantity in ["", "-", "0", "None", "null"]:
                continue

            try:
                quantity = int(float(quantity))
            except ValueError:
                continue

            relief.append({
                "report_date": report_date,
                "report_number": report_number,
                "province": province,
                "item": item,
                "quantity": quantity
            })

    # -----------------------
    # Rescue
    # -----------------------

    for row in report["rescue"]:

        row["report_date"] = report_date
        row["report_number"] = report_number

        rescue.append(row)

# -----------------------
# Save Analytics Datasets
# -----------------------

save_json(
    casualties,
    OUTPUT_FOLDER / "casualties.json"
)

save_json(
    damage,
    OUTPUT_FOLDER / "damage.json"
)

save_json(
    relief,
    OUTPUT_FOLDER / "relief.json"
)

save_json(
    rescue,
    OUTPUT_FOLDER / "rescue.json"
)

print("=" * 60)
print("DATASETS CREATED")
print("=" * 60)
print("Casualties :", len(casualties))
print("Damage     :", len(damage))
print("Relief     :", len(relief))
print("Rescue     :", len(rescue))
print("=" * 60)