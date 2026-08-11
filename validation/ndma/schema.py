from pathlib import Path

REQUIRED_TABLES = [
    "casualties",
    "damage",
    "relief",
    "rescue",
]

REQUIRED_FIELDS = {
    "casualties": [
        "province",
        "deaths",
        "injured",
    ],

    "damage": [
        "province",
        "houses_damaged",
    ],

    "relief": [
        "province",
    ],

    "rescue": [
        "province",
    ],
}


def validate_schema(parsed_tables):

    errors = []

    # -----------------------------
    # Required Tables
    # -----------------------------

    for table in REQUIRED_TABLES:

        if table not in parsed_tables:

            errors.append(f"Missing table : {table}")

            continue

        if len(parsed_tables[table]) == 0:

            errors.append(f"Empty table : {table}")

    # -----------------------------
    # Required Columns
    # -----------------------------

    for table, columns in REQUIRED_FIELDS.items():

        if table not in parsed_tables:
            continue

        rows = parsed_tables[table]

        if not rows:
            continue

        first = rows[0]

        for col in columns:

            if col not in first:

                errors.append(
                    f"{table} missing column : {col}"
                )

    return len(errors) == 0, errors