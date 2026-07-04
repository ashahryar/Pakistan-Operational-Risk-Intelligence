from sqlalchemy import create_engine, text
from datetime import datetime
import json
from pathlib import Path

# ==========================
# DATABASE CONFIGURATION
# ==========================

DATABASE_URL = "postgresql+psycopg2://postgres:123456789@localhost:5432/pakistan_operational_risk"

engine = create_engine(DATABASE_URL)

TABLES = [
    "ndma_casualties",
    "ndma_damage",
    "ndma_relief",
    "ndma_rescue"
]

# ==========================
# HELPER FUNCTIONS
# ==========================

def run_scalar(query):
    with engine.connect() as conn:
        return conn.execute(text(query)).scalar()


def column_exists(table, column):
    query = f"""
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name='{table}'
        AND column_name='{column}'
    );
    """
    return run_scalar(query)


# ==========================
# TABLE AUDIT
# ==========================

def audit_table(table):

    report = {}

    # -----------------------
    # Total Rows
    # -----------------------
    report["rows"] = run_scalar(
        f"SELECT COUNT(*) FROM {table}"
    )

    # -----------------------
    # Province Checks
    # -----------------------
    if column_exists(table, "province"):

        report["blank_province"] = run_scalar(f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE province IS NULL
            OR TRIM(province)='';
        """)

        report["grand_total_rows"] = run_scalar(f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE LOWER(province) LIKE '%total%';
        """)

    # -----------------------
    # Quantity Checks
    # -----------------------
    if column_exists(table, "quantity"):

        report["null_quantity"] = run_scalar(f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE quantity IS NULL;
        """)

        report["zero_quantity"] = run_scalar(f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE quantity=0;
        """)

        report["negative_quantity"] = run_scalar(f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE quantity<0;
        """)

    # -----------------------
    # Report Date
    # -----------------------
    if column_exists(table, "report_date"):

        report["null_report_date"] = run_scalar(f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE report_date IS NULL;
        """)

    # -----------------------
    # Duplicate Detection
    # -----------------------

    duplicate_columns = []

    if column_exists(table, "report_number"):
        duplicate_columns.append("report_number")

    if column_exists(table, "province"):
        duplicate_columns.append("province")

    if column_exists(table, "item"):
        duplicate_columns.append("item")

    if column_exists(table, "quantity"):
        duplicate_columns.append("quantity")

    if duplicate_columns:

        cols = ", ".join(duplicate_columns)

        duplicate_query = f"""
        SELECT COUNT(*)
        FROM (
            SELECT {cols}
            FROM {table}
            GROUP BY {cols}
            HAVING COUNT(*) > 1
        ) x;
        """

        report["duplicate_groups"] = run_scalar(duplicate_query)

    return report


# ==========================
# MAIN
# ==========================

def main():

    final_report = {
        "generated_at": datetime.now().isoformat(),
        "tables": {}
    }

    print("\n" + "=" * 70)
    print(" NDMA DATA QUALITY AUDIT")
    print("=" * 70)

    for table in TABLES:

        print(f"\nTable : {table}")

        result = audit_table(table)

        final_report["tables"][table] = result

        for key, value in result.items():
            print(f"{key:<25}: {value}")

    # -----------------------
    # Save JSON Report
    # -----------------------

    output_dir = Path("logs")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "ndma_data_quality_report.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=4)

    print("\n" + "=" * 70)
    print(f"Report saved to: {output_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()