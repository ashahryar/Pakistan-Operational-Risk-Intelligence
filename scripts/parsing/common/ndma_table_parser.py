"""
NDMA table parser.
Converts raw PDF tables into structured data.
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

    # -------------------------------------------------------
    # Duplicate Tracking
    # -------------------------------------------------------

    casualty_seen = set()
    damage_seen = set()
    relief_seen = set()
    rescue_seen = set()

    # -------------------------------------------------------
    # Loop tables
    # -------------------------------------------------------

    for table in tables:

        if not table:
            continue

        header = " ".join(
            str(c)
            for c in table[0]
            if c
        ).lower()

        # =====================================================
        # CASUALTIES
        # =====================================================

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

        # =====================================================
        # DAMAGE
        # =====================================================

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

                    "houses_full": value(row, 3),

                    "houses_partial": value(row, 4),

                    "houses_total": value(row, 5),

                    "livestock": value(row, 6),

                })

        # =====================================================
        # RELIEF
        # =====================================================

        elif "flood activity item" in header or "relief items" in header:

            for row in table[1:]:

                if not row:
                    continue

                item = value(row, 0)

                if item in (None, ""):
                    continue

                key = tuple(
                    value(row, i)
                    for i in range(len(row))
                )

                if key in relief_seen:
                    continue

                relief_seen.add(key)

                cleaned = [
                    value(row, i)
                    for i in range(len(row))
                ]

                data["relief"].append(cleaned)

        # =====================================================
        # RESCUE
        # =====================================================

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