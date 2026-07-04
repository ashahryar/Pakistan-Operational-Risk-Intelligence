"""
NDMA table parser.
Converts raw PDF tables into structured data.
"""
def value(row, index):

    if index < len(row):
        return row[index]

    return None

def parse_tables(tables):

    data = {
        "casualties": [],
        "damage": [],
        "relief": [],
        "rescue": []
    }

    for table in tables:

        if not table:
            continue

        header = " ".join(
            str(cell)
            for cell in table[0]
            if cell
        ).lower()

        # -------------------------------------
        # Casualties
        # -------------------------------------

        if "province" in header and "deceased" in header:

            for row in table[2:]:

                if not row:
                    continue

                if row[0] is None:
                    continue

                data["casualties"].append({

                    "province": value(row, 0),
                    "deaths": value(row, 4),
                    "injured": value(row, 8),
                })
        # -------------------------------------
        # Damage
        # -------------------------------------

        elif "roads" in header and "bridges" in header:

            for row in table[2:]:

                if not row:
                    continue

                data["damage"].append({

                    "province": value(row, 0),

                    "roads_km": value(row, 1),

                    "bridges": value(row, 2),

                    "houses_full": value(row, 3),

                    "houses_partial": value(row, 4),

                    "houses_total": value(row, 5),

                    "livestock": value(row, 6),

            })
        # -------------------------------------
        # Relief
        # -------------------------------------

        elif "flood activity item" in header or "relief items" in header:

            for row in table[1:]:

                if not row:
                    continue

                data["relief"].append(row)

        # -------------------------------------
        # Rescue
        # -------------------------------------

        elif "rescue operation" in header:

            for row in table[1:]:

                if not row:
                    continue

                data["rescue"].append({

                    "province": value(row, 0),

                    "operations": value(row, 1),

                    "rescued": value(row, 2),

                })
                print(row)

    return data