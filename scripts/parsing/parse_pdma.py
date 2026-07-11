"""
PDMA Parsing Pipeline

Runs all PDMA parsers.

Daily Reports
Rainfall Reports
Gauge Reports
"""

from pathlib import Path
import json

from parse_pdma_daily import parse_pdf as parse_daily
from parse_rainfall import parse_rainfall_report as parse_rainfall
from parse_gauge import parse_pdf as parse_gauge


RAW_DIR = Path("data/raw/pdma/reports")
OUTPUT_DIR = Path("data/parsed/pdma")


REPORTS = {
    "daily_reports": parse_daily,
    "rainfall_reports": parse_rainfall,
    "gauge_reports": parse_gauge,
}


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


def process_report(report_name, parser):

    report_dir = RAW_DIR / report_name

    if not report_dir.exists():

        print(f"{report_dir} not found")

        return

    for year_folder in sorted(report_dir.iterdir()):

        if not year_folder.is_dir():

            continue

        pdf_dir = year_folder / "pdfs"

        if not pdf_dir.exists():

            continue

        parsed_folder_name = report_name.replace("_reports", "")
        output_dir = OUTPUT_DIR / parsed_folder_name / year_folder.name

        pdf_files = sorted(pdf_dir.glob("*.pdf"))

        print("=" * 60)
        print(report_name)
        print(year_folder.name)
        print(f"PDFs : {len(pdf_files)}")
        print("=" * 60)

        for pdf in pdf_files:

            try:

                parsed = parser(pdf)

                output_file = output_dir / f"{pdf.stem}.json"

                save_json(
                    parsed,
                    output_file,
                )

                print(f"[OK] Parsed : {pdf.name}")

            except Exception as e:

                print(f"[FAIL] Failed : {pdf.name}")

                print(e)


def main():

    for report_name, parser in REPORTS.items():

        process_report(
            report_name,
            parser,
        )


if __name__ == "__main__":

    main()