import json
import sys
from pathlib import Path

from scripts.parsing.pmd.daily_parser import parse_daily_forecast
from scripts.parsing.pmd.weekly_parser import parse_weekly_outlook
from scripts.parsing.pmd.alerts_parser import parse_weather_alert

from config.data_quality import REJECTION_THRESHOLD
from pipeline.utils.quarantine import write_quarantine
from validation.pmd.schema import validate_daily, validate_weekly, validate_alert

OUTPUT_DIR = Path("data/parsed/pmd")

RAW_FILE = {
    "daily_forecast": Path("data/raw/pmd/reports/daily_forecast/all/latest.json"),
    "weekly_outlook": Path("data/raw/pmd/reports/weekly_outlook/all/latest.json"),
    "weather_alerts": Path("data/raw/pmd/reports/weather_alerts/all/latest.json"),
}

PARSER_VERSION = "1.0.0"


def _apply_schema_gate(records, validate_fn, domain):
    """
    Phase 1 / Task 16A (ADR-0001) -- wires the existing, previously-
    unused validation.pmd.schema module into the SAME quarantine/
    rejection-ratio DQ framework Task 5 already built for NDMA/PDMA,
    rather than adding a second validation system.

    daily_parser.py/weekly_parser.py already quarantine structurally
    malformed *raw table rows* before they ever become a parsed
    record (row_too_short / failed_weather_validation). This is a
    second, independent check on the parser's *output* -- did the
    fully-parsed record actually end up with every schema-required
    field populated? A parser bug could in principle produce a
    well-formed-looking but incomplete record that the row-level
    checks wouldn't catch.

    `validate_fn` is validate_daily or validate_weekly, both of which
    accept a list and validate every row's required fields. Each
    record is checked individually (as a length-1 list) so a failure
    can be attributed, quarantined, and dropped one record at a time,
    instead of failing the whole batch.

    Returns (kept_records, additional_rejected_count).
    """
    kept = []
    additional_rejected = 0

    for record in records:
        is_valid, errors = validate_fn([record])
        if is_valid:
            kept.append(record)
        else:
            additional_rejected += 1
            write_quarantine(
                source="pmd",
                domain=domain,
                source_document=str(RAW_FILE.get(domain, "")),
                reason_code="schema_invalid",
                message="; ".join(errors),
                parser_version=PARSER_VERSION,
                raw_payload=record,
            )

    return kept, additional_rejected

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

    daily, schema_rejected_daily = _apply_schema_gate(daily, validate_daily, "daily_forecast")
    daily_rejected += schema_rejected_daily

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

    weekly, schema_rejected_weekly = _apply_schema_gate(weekly, validate_weekly, "weekly_outlook")
    weekly_rejected += schema_rejected_weekly

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

    # alerts_parser produces a single alert object per run (no per-record
    # loop of its own) -- validated here as one record, same as daily/weekly.
    alerts_processed, alerts_rejected = 1, 0
    alert_is_valid, alert_errors = validate_alert(alerts)
    if not alert_is_valid:
        alerts_rejected = 1
        write_quarantine(
            source="pmd",
            domain="weather_alerts",
            source_document=str(RAW_FILE["weather_alerts"]),
            reason_code="schema_invalid",
            message="; ".join(alert_errors),
            parser_version=PARSER_VERSION,
            raw_payload=alerts,
        )

    save_json(
        alerts,
        OUTPUT_DIR / "weather_alerts" / "latest.json"
    )

    print(f"✓ Weather Alert Parsed | Schema valid : {alert_is_valid}")

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