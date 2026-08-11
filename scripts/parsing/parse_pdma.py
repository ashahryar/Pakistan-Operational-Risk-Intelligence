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

        return

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

    print()
    print("-" * 60)
    print(report_name)
    print(f"Processed : {total}")
    print(f"Saved     : {saved}")
    print(f"Rejected  : {rejected}")
    print("-" * 60)
    print()


# ==========================================================
# MAIN
# ==========================================================

def main():

    print("=" * 70)
    print("PDMA PARSING PIPELINE")
    print("=" * 70)

    for report_name, parser in REPORTS.items():

        process_report(
            report_name,
            parser,
        )

    print("=" * 70)
    print("PDMA PARSING COMPLETED")
    print("=" * 70)


if __name__ == "__main__":

    main()