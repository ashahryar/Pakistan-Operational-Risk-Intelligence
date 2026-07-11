import json
from pathlib import Path

from scripts.parsing.pmd.daily_parser import parse_daily_forecast
from scripts.parsing.pmd.weekly_parser import parse_weekly_outlook
from scripts.parsing.pmd.alerts_parser import parse_weather_alert


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

    daily = parse_daily_forecast()

    save_json(
        daily,
        OUTPUT_DIR / "daily_forecast" / "latest.json"
    )

    print(f"✓ Daily Forecast Parsed ({len(daily)} cities)")

    # ----------------------------------------------------
    # Weekly Outlook
    # ----------------------------------------------------

    print("\nParsing Weekly Outlook...")

    weekly = parse_weekly_outlook()

    save_json(
        weekly,
        OUTPUT_DIR / "weekly_outlook" / "latest.json"
    )

    print(f"✓ Weekly Outlook Parsed ({len(weekly)} days)")

    # ----------------------------------------------------
    # Weather Alerts
    # ----------------------------------------------------

    print("\nParsing Weather Alerts...")

    alerts = parse_weather_alert()

    save_json(
        alerts,
        OUTPUT_DIR / "weather_alerts" / "latest.json"
    )

    print("✓ Weather Alert Parsed")

    print("\n" + "=" * 60)
    print("PMD PARSING COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()