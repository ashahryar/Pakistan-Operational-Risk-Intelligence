"""
NDMA Table Parser
Converts extracted PDF tables into structured JSON
"""

def value(row, index):
    if index < len(row):
        cell = row[index]

        if cell is None:
            return None

        cell = str(cell).strip()

        if cell == "":
            return None

        return cell

    return None


def parse_tables(tables):

    data = {
        "casualties": [],
        "damage": [],
        "relief": [],
        "rescue": [],
    }

    casualty_seen = set()
    damage_seen = set()
    relief_seen = set()
    rescue_seen = set()

    for table in tables:

        if not table:
            continue

        header = " ".join(
            str(c) for c in table[0] if c
        ).lower()

        # =========================================================
        # CASUALTIES
        # =========================================================

        if "province" in header and "deceased" in header:

            for row in table[2:]:

                province = value(row, 0)

                if province in (None, "", "Grand Total"):
                    continue

                key = (
                    province,
                    value(row, 4),
                    value(row, 8),
                )

                if key in casualty_seen:
                    continue

                casualty_seen.add(key)

                data["casualties"].append({

                    "province": province,

                    "deaths": value(row, 4),

                    "injured": value(row, 8),

                })

        # =========================================================
        # DAMAGE
        # =========================================================

        elif "roads" in header and "bridges" in header:

            for row in table[2:]:

                province = value(row, 0)

                if province in (None, "", "Grand Total"):
                    continue

                key = (
                    province,
                    value(row, 5),
                )

                if key in damage_seen:
                    continue

                damage_seen.add(key)

                data["damage"].append({

                    "province": province,

                    "roads_km": value(row, 1),

                    "bridges": value(row, 2),

                    "houses_fully_damaged": value(row, 3),

                    "houses_partially_damaged": value(row, 4),

                    "houses_damaged": value(row, 5),

                    "livestock": value(row, 6),

                })

        # =========================================================
        # RELIEF
        # =========================================================

        elif (
            "flood activity item" in header
            or "relief items" in header
            or "relief item" in header
        ):

            for row in table[1:]:

                if not row:
                    continue

                province = value(row, 0)

                item = value(row, 1)

                quantity = value(row, 2)

                if province is None and item is None:
                    continue

                key = (
                    province,
                    item,
                    quantity,
                )

                if key in relief_seen:
                    continue

                relief_seen.add(key)

                data["relief"].append({

                    "province": province,

                    "item": item,

                    "quantity": quantity,

                })

        # =========================================================
        # RESCUE
        # =========================================================

        elif "rescue operation" in header:

            for row in table[1:]:

                province = value(row, 0)

                if province in (None, "", "Grand Total"):
                    continue

                key = (
                    province,
                    value(row, 1),
                    value(row, 2),
                )

                if key in rescue_seen:
                    continue

                rescue_seen.add(key)

                data["rescue"].append({

                    "province": province,

                    "operations": value(row, 1),

                    "rescued": value(row, 2),

                })

    return data