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

for file in sorted(INPUT_FOLDER.glob("*.json")):

    with open(file, encoding="utf8") as f:
        report = json.load(f)

    report_date = report["report_date"]
    report_number = report["report_number"]

    # =====================================================
    # CASUALTIES
    # =====================================================

    seen_casualties = set()

    for row in report.get("casualties", []):

        province = str(row.get("province", "")).strip()

        # Skip invalid rows
        if province in ("", "Grand Total"):
            continue

        key = (report_number, report_date, province)

        if key in seen_casualties:
            continue

        seen_casualties.add(key)

        casualties.append({
            "report_number": report_number,
            "report_date": report_date,
            "province": province,
            "deaths": row.get("deaths"),
            "injured": row.get("injured"),
        })

    # =====================================================
    # DAMAGE
    # =====================================================

    seen_damage = set()

    for row in report.get("damage", []):

        province = str(row.get("province", "")).strip()

        if province in ("", "Grand Total"):
            continue

        key = (report_number, report_date, province)

        if key in seen_damage:
            continue

        seen_damage.add(key)

        damage.append({
            "report_number": report_number,
            "report_date": report_date,
            "province": province,
            "roads_km": row.get("roads_km"),
            "bridges": row.get("bridges"),
            "houses_total": row.get("houses_total"),
            "livestock": row.get("livestock"),
        })

    # =====================================================
    # RELIEF
    # =====================================================

    for row in report.get("relief", []):

        if len(row) < len(provinces) + 1:
            continue

        item = str(row[0]).strip()

        for i, province in enumerate(provinces):

            quantity = str(row[i + 1]).strip()

            if quantity in ("", "-", "0", "None", "null"):
                continue

            try:
                quantity = int(float(quantity))
            except ValueError:
                continue

            relief.append({
                "report_number": report_number,
                "report_date": report_date,
                "province": province,
                "item": item,
                "quantity": quantity,
            })

    # =====================================================
    # RESCUE
    # =====================================================

    seen_rescue = set()

    for row in report.get("rescue", []):

        province = str(row.get("province", "")).strip()

        if province in ("", "Grand Total"):
            continue

        key = (report_number, report_date, province)

        if key in seen_rescue:
            continue

        seen_rescue.add(key)

        rescue.append({
            "report_number": report_number,
            "report_date": report_date,
            "province": province,
            "operations": row.get("operations"),
            "rescued": row.get("rescued"),
        })


def remove_duplicates(rows, keys):
    seen = set()
    cleaned = []

    for row in rows:
        key = tuple(row.get(k) for k in keys)

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(row)

    return cleaned
casualties = remove_duplicates(
    casualties,
    ["report_number", "report_date", "province"]
)

damage = remove_duplicates(
    damage,
    ["report_number", "report_date", "province"]
)

relief = remove_duplicates(
    relief,
    [
        "report_number",
        "report_date",
        "province",
        "item"
    ]
)

rescue = remove_duplicates(
    rescue,
    ["report_number", "report_date", "province"]
)

# =====================================================
# SAVE DATASETS
# =====================================================

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
print("NDMA ANALYTICS DATASETS CREATED")
print("=" * 60)
print(f"Casualties : {len(casualties)}")
print(f"Damage     : {len(damage)}")
print(f"Relief     : {len(relief)}")
print(f"Rescue     : {len(rescue)}")
print("=" * 60)