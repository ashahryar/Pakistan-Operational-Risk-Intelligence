"""
pipeline/helpers/redshift_helper.py

Reusable Amazon Redshift Helper

Supports

• Connection
• Query Execution
• Fetch Results
• Table Verification
"""

import os
from pathlib import Path

import redshift_connector

from dotenv import load_dotenv


# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


# ==========================================================
# REDSHIFT CONFIGURATION
# ==========================================================

REDSHIFT_HOST = os.getenv("REDSHIFT_HOST")

REDSHIFT_PORT = int(

    os.getenv(

        "REDSHIFT_PORT",

        5439,

    )

)

REDSHIFT_DATABASE = os.getenv(

    "REDSHIFT_DB"

)

REDSHIFT_USER = os.getenv(

    "REDSHIFT_USER"

)

REDSHIFT_PASSWORD = os.getenv(

    "REDSHIFT_PASSWORD"

)


# ==========================================================
# CONNECTION
# ==========================================================

def get_connection():
    """
    Create Redshift connection.
    """

    try:

        connection = redshift_connector.connect(

            host=REDSHIFT_HOST,

            port=REDSHIFT_PORT,

            database=REDSHIFT_DATABASE,

            user=REDSHIFT_USER,

            password=REDSHIFT_PASSWORD,

        )

        return connection

    except Exception as e:

        raise RuntimeError(

            f"Unable to connect to Redshift : {e}"

        )
# ==========================================================
# EXECUTE QUERY
# ==========================================================

def execute(sql, params=None):
    """
    Execute INSERT / UPDATE / DELETE query.
    """

    conn = get_connection()

    cur = conn.cursor()

    try:

        cur.execute(sql, params)

        conn.commit()

    except Exception as e:

        conn.rollback()

        raise RuntimeError(

            f"Query Execution Failed : {e}"

        )

    finally:

        cur.close()

        conn.close()


# ==========================================================
# FETCH ALL
# ==========================================================

def fetch(sql, params=None):
    """
    Fetch multiple rows.
    """

    conn = get_connection()

    cur = conn.cursor()

    try:

        cur.execute(sql, params)

        rows = cur.fetchall()

        return rows

    finally:

        cur.close()

        conn.close()


# ==========================================================
# FETCH ONE
# ==========================================================

def fetch_one(sql, params=None):
    """
    Fetch single row.
    """

    conn = get_connection()

    cur = conn.cursor()

    try:

        cur.execute(sql, params)

        row = cur.fetchone()

        return row

    finally:

        cur.close()

        conn.close()


# ==========================================================
# TABLE EXISTS
# ==========================================================

def table_exists(table_name):
    """
    Check if a table exists.
    """

    sql = """

    SELECT EXISTS(

        SELECT 1

        FROM information_schema.tables

        WHERE table_name = %s

    )

    """

    row = fetch_one(

        sql,

        (table_name,)

    )

    return row[0]


# ==========================================================
# VERIFY TABLES
# ==========================================================

def verify_tables(table_list):
    """
    Verify all Redshift tables contain data.
    """

    print("=" * 60)
    print("VERIFY REDSHIFT TABLES")
    print("=" * 60)

    failed = []

    for table in table_list:

        try:

            if not table_exists(table):

                print(f"{table:<35} MISSING")

                failed.append(table)

                continue

            count = fetch_one(

                f"SELECT COUNT(*) FROM {table}"

            )[0]

            print(f"{table:<35} {count}")

            if count == 0:

                failed.append(table)

        except Exception as e:

            print(f"{table:<35} ERROR")

            print(e)

            failed.append(table)

    print("=" * 60)

    if failed:

        raise RuntimeError(

            f"Verification Failed : {failed}"

        )

    print("Redshift Verification Successful")

    print("=" * 60)


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("REDSHIFT HELPER TEST")
    print("=" * 60)

    tables = [

        "ndma_casualties",

        "ndma_damage",

        "ndma_relief",

        "ndma_rescue",

        "pdma_rainfall",

        "pdma_rivers",

        "pmd_daily_forecast",

        "pmd_weekly_outlook",

        "pmd_weather_alerts",

    ]

    verify_tables(tables)