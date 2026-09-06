import json
import sys
from pathlib import Path

from scripts.parsing.pmd.daily_parser import parse_daily_forecast
from scripts.parsing.pmd.weekly_parser import parse_weekly_outlook
from scripts.parsing.pmd.alerts_parser import parse_weather_alert

from config.data_quality import REJECTION_THRESHOLD

OUTPUT_DIR = Path("data/parsed/pmd")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_json(data, output_file):

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(output_file, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False,
            default=str
        )


def main():

    print("=" * 60)
    print("PMD PARSING PIPELINE")
    print("=" * 60)

    # ----------------------------------------------------
    # Daily Forecast
    # ----------------------------------------------------

    print("\nParsing Daily Forecast...")

    daily, daily_processed, daily_rejected = parse_daily_forecast()

    save_json(
        daily,
        OUTPUT_DIR / "daily_forecast" / "latest.json"
    )

    print(f"✓ Daily Forecast Parsed ({len(daily)} cities) | Processed : {daily_processed} | Rejected : {daily_rejected}")

    # ----------------------------------------------------
    # Weekly Outlook
    # ----------------------------------------------------

    print("\nParsing Weekly Outlook...")

    weekly, weekly_processed, weekly_rejected = parse_weekly_outlook()

    save_json(
        weekly,
        OUTPUT_DIR / "weekly_outlook" / "latest.json"
    )

    print(f"✓ Weekly Outlook Parsed ({len(weekly)} days) | Processed : {weekly_processed} | Rejected : {weekly_rejected}")

    # ----------------------------------------------------
    # Weather Alerts
    # ----------------------------------------------------

    print("\nParsing Weather Alerts...")

    alerts = parse_weather_alert()

    save_json(
        alerts,
        OUTPUT_DIR / "weather_alerts" / "latest.json"
    )

    # alerts_parser has no per-record loop (single alert object per run) —
    # treated as one processed, zero rejected for the purposes of this gate.
    alerts_processed, alerts_rejected = 1, 0

    print("✓ Weather Alert Parsed")

    grand_processed = daily_processed + weekly_processed + alerts_processed
    grand_rejected = daily_rejected + weekly_rejected + alerts_rejected

    print("\n" + "=" * 60)
    print("PMD PARSING COMPLETED")
    print(f"Total Processed : {grand_processed}")
    print(f"Total Rejected  : {grand_rejected}")
    print("=" * 60)

    # ------------------------------------------------------
    # DATA QUALITY GATE (Phase 1 / Task 5, ADR-0001, CLAUDE.md rule 5)
    # ------------------------------------------------------

    if grand_processed == 0:
        return

    rejection_ratio = grand_rejected / grand_processed

    print(f"Rejection Ratio      : {round(rejection_ratio * 100, 2)}%")
    print(f"Rejection Threshold  : {round(REJECTION_THRESHOLD * 100, 2)}%")

    if rejection_ratio > REJECTION_THRESHOLD:

        print("=" * 60)
        print("DATA QUALITY GATE FAILED")
        print(f"{grand_rejected}/{grand_processed} records rejected — exceeds threshold")
        print("=" * 60)

        sys.exit(1)


if __name__ == "__main__":
    main()