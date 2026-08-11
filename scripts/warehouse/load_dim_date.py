import sys
from pathlib import Path
from datetime import datetime, date

from sqlalchemy import text

# ==========================================================
# PROJECT ROOT
# ==========================================================

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine

# ==========================================================
# GET UNIQUE DATES
# ==========================================================

SQL = """
SELECT report_date FROM ndma_casualties

UNION

SELECT report_date FROM ndma_damage

UNION

SELECT report_date FROM ndma_relief

UNION

SELECT report_date FROM ndma_rescue

UNION

SELECT report_date FROM pdma_daily_reports

ORDER BY 1;
"""

# ==========================================================
# LOAD DIM_DATE
# ==========================================================

def load_dim_date():

    inserted = 0

    with engine.begin() as conn:

        rows = conn.execute(text(SQL)).fetchall()

        for row in rows:

            report_date = row[0]

            if report_date is None:
                continue

            # ---------------------------------------
            # Convert to Python date
            # ---------------------------------------

            if isinstance(report_date, str):

                try:
                    report_date = datetime.strptime(
                        report_date,
                        "%d %B %Y"
                    ).date()

                except:

                    try:
                        report_date = datetime.strptime(
                            report_date,
                            "%Y-%m-%d"
                        ).date()

                    except:
                        continue

            elif isinstance(report_date, datetime):

                report_date = report_date.date()

            elif not isinstance(report_date, date):

                continue

            # ---------------------------------------
            # Insert
            # ---------------------------------------

            conn.execute(
                text(
                    """
                    INSERT INTO dim_date (

                        date_key,
                        full_date,
                        day,
                        month,
                        month_name,
                        quarter,
                        year,
                        week,
                        weekday,
                        weekday_name,
                        is_weekend

                    )

                    VALUES (

                        :date_key,
                        :full_date,
                        :day,
                        :month,
                        :month_name,
                        :quarter,
                        :year,
                        :week,
                        :weekday,
                        :weekday_name,
                        :is_weekend

                    )

                    ON CONFLICT (full_date)
                    DO NOTHING
                    """
                ),
                {
                    "date_key": int(report_date.strftime("%Y%m%d")),
                    "full_date": report_date,
                    "day": report_date.day,
                    "month": report_date.month,
                    "month_name": report_date.strftime("%B"),
                    "quarter": (report_date.month - 1) // 3 + 1,
                    "year": report_date.year,
                    "week": report_date.isocalendar()[1],
                    "weekday": report_date.isoweekday(),
                    "weekday_name": report_date.strftime("%A"),
                    "is_weekend": report_date.weekday() >= 5,
                },
            )

            inserted += 1

    print("=" * 60)
    print("DIM_DATE LOADED")
    print("=" * 60)
    print(f"Dates Processed : {inserted}")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    load_dim_date()


if __name__ == "__main__":
    main()