import os

import redshift_connector

from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def verify_tables(table_list):

    conn = redshift_connector.connect(

        host=os.getenv("REDSHIFT_HOST"),

        port=int(
            os.getenv(
                "REDSHIFT_PORT",
                5439
            )
        ),

        database=os.getenv("REDSHIFT_DB"),

        user=os.getenv("REDSHIFT_USER"),

        password=os.getenv(
            "REDSHIFT_PASSWORD"
        )
    )

    cur = conn.cursor()

    empty = []

    for table in table_list:

        cur.execute(
            f"SELECT COUNT(*) FROM {table}"
        )

        count = cur.fetchone()[0]

        print(table, count)

        if count == 0:
            empty.append(table)

    cur.close()
    conn.close()

    if empty:
        raise RuntimeError(
            f"Empty tables: {empty}"
        )