"""
PDMA Parsing Pipeline

Runs all PDMA parsers.

Daily Reports
Rainfall Reports
Gauge Reports

Only VALID reports are saved.
"""

from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from validation.pdma.schema import validate_schema
from validation.pdma.completeness import completeness_score
from validation.pdma.score import quality_score

from parse_pdma_daily import parse_pdf as parse_daily
from parse_rainfall import parse_rainfall_report as parse_rainfall
from parse_gauge import parse_pdf as parse_gauge

# ==========================================================
# DATA QUALITY (Phase 1 / Task 5, ADR-0001)
# ==========================================================

from pipeline.utils.quarantine import write_quarantine
from config.data_quality import REJECTION_THRESHOLD

PARSER_VERSION = "1.0.0"


# ==========================================================
# PATHS
# ==========================================================

RAW_DIR = Path("data/raw/pdma/reports")

OUTPUT_DIR = Path("data/parsed/pdma")


REPORTS = {

    "daily_reports": parse_daily,

    "rainfall_reports": parse_rainfall,

    "gauge_reports": parse_gauge,

}


# ==========================================================
# SAVE JSON
# ==========================================================

def save_json(data, output_path):

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
            default=str,
        )


# ==========================================================
# PROCESS REPORTS
# ==========================================================

def process_report(report_name, parser):

    report_dir = RAW_DIR / report_name

    if not report_dir.exists():

        print(f"{report_dir} not found")

        return 0, 0, 0

    total = 0
    saved = 0
    rejected = 0

    for year_folder in sorted(report_dir.iterdir()):

        if not year_folder.is_dir():
            continue

        pdf_dir = year_folder / "pdfs"

        if not pdf_dir.exists():
            continue

        parsed_folder = report_name.replace("_reports", "")

        output_dir = OUTPUT_DIR / parsed_folder / year_folder.name

        pdf_files = sorted(pdf_dir.glob("*.pdf"))

        print("=" * 60)
        print(report_name)
        print(year_folder.name)
        print(f"PDFs : {len(pdf_files)}")
        print("=" * 60)

        for pdf in pdf_files:

            total += 1

            try:

                parsed = parser(pdf)

                # ----------------------------------
                # Validation
                # ----------------------------------

                valid, errors = validate_schema(parsed)

                completeness = completeness_score(parsed)

                score = quality_score(parsed)

                parsed["validation"] = {

                    "valid": valid,

                    "errors": errors,

                    "completeness": completeness,

                    "quality_score": score,

                    }

                if not valid:

                    rejected += 1

                    print(f"[INVALID] {pdf.name}")

                    for err in errors:
                        print("   -", err)

                    write_quarantine(
                        source="pdma",
                        domain=report_name.replace("_reports", ""),
                        source_document=str(pdf),
                        reason_code="schema_invalid",
                        message="; ".join(errors) if errors else "Schema validation failed",
                        parser_version=PARSER_VERSION,
                        raw_payload=parsed,
                    )

                    continue

                output_file = output_dir / f"{pdf.stem}.json"

                save_json(
                    parsed,
                    output_file,
                )

                saved += 1

                print(
                    f"[OK] {pdf.name} | "
                    f"Score={score['score']}% | "
                    f"Completeness={completeness['score']}%"
                )

            except Exception as e:

                rejected += 1

                print(f"[FAIL] {pdf.name}")

                print(e)

                write_quarantine(
                    source="pdma",
                    domain=report_name.replace("_reports", ""),
                    source_document=str(pdf),
                    reason_code="unhandled_exception",
                    message=str(e),
                    parser_version=PARSER_VERSION,
                )

    print()
    print("-" * 60)
    print(report_name)
    print(f"Processed : {total}")
    print(f"Saved     : {saved}")
    print(f"Rejected  : {rejected}")
    print("-" * 60)
    print()

    return total, saved, rejected


# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 70)
    print("PDMA PARSING PIPELINE")
    print("=" * 70)

    grand_total = 0
    grand_saved = 0
    grand_rejected = 0

    for report_name, parser in REPORTS.items():

        total, saved, rejected = process_report(
            report_name,
            parser,
        )

        grand_total += total
        grand_saved += saved
        grand_rejected += rejected

    print("=" * 70)
    print("PDMA PARSING COMPLETED")
    print(f"Total Processed : {grand_total}")
    print(f"Total Saved     : {grand_saved}")
    print(f"Total Rejected  : {grand_rejected}")
    print("=" * 70)

    # ------------------------------------------------------
    # DATA QUALITY GATE (Phase 1 / Task 5, ADR-0001, CLAUDE.md rule 5)
    # ------------------------------------------------------

    if grand_total == 0:
        return

    rejection_ratio = grand_rejected / grand_total

    print(f"Rejection Ratio      : {round(rejection_ratio * 100, 2)}%")
    print(f"Rejection Threshold  : {round(REJECTION_THRESHOLD * 100, 2)}%")

    if rejection_ratio > REJECTION_THRESHOLD:

        print("=" * 70)
        print("DATA QUALITY GATE FAILED")
        print(f"{grand_rejected}/{grand_total} files rejected — exceeds threshold")
        print("=" * 70)

        sys.exit(1)


if __name__ == "__main__":

    main()