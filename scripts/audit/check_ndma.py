import sys
from pathlib import Path

from sqlalchemy import text

# Project Root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.database.connection import engine

CHECKS = [
    (
        "Grand Total Rows",
        """
        SELECT COUNT(*)
        FROM ndma_relief
        WHERE LOWER(province) LIKE '%total%';
        """
    ),

    (
        "Blank Province",
        """
        SELECT COUNT(*)
        FROM ndma_relief
        WHERE province IS NULL
        OR TRIM(province) = '';
        """
    ),

    (
        "Duplicate Relief Records",
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                report_number,
                report_date,
                province,
                item,
                quantity
            FROM ndma_relief
            GROUP BY
                report_number,
                report_date,
                province,
                item,
                quantity
            HAVING COUNT(*) > 1
        ) x;
        """
    ),

    (
        "Zero Quantity",
        """
        SELECT COUNT(*)
        FROM ndma_relief
        WHERE quantity = 0;
        """
    )
]

print("\n" + "=" * 50)
print("NDMA DATA QUALITY CHECK")
print("=" * 50)

with engine.connect() as conn:
    for title, query in CHECKS:
        result = conn.execute(text(query)).scalar()
        print(f"{title:<30}: {result}")

print("=" * 50)