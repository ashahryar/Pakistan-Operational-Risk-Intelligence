import json
from pathlib import Path

from scripts.parsing.pdma.daily_parser import parse_daily_report
from scripts.parsing.pdma.rainfall_parser import parse_rainfall_report
from scripts.parsing.pdma.gauge_parser import parse_gauge_report


RAW_DIR = Path("data/raw/pdma/reports")
OUTPUT_DIR = Path("data/parsed/pdma")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


REPORT_TYPES = {
    "daily_reports": parse_daily_report,
    "rainfall_reports": parse_rainfall_report,
    "gauge_reports": parse_gauge_report,
}


def save_json(data, output_file):

    with open(output_file, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False,
            default=str
        )


def process_report(report_name, parser):

    report_folder = RAW_DIR / report_name

    if not report_folder.exists():
        print(f"{report_folder} not found")
        return

    for year in report_folder.iterdir():

        pdf_dir = year / "pdfs"

        if not pdf_dir.exists():
            continue

        output_year = OUTPUT_DIR / report_name / year.name

        output_year.mkdir(
            parents=True,
            exist_ok=True
        )

        pdfs = list(pdf_dir.glob("*.pdf"))

        print(f"\n{report_name} | {year.name}")
        print(f"PDFs : {len(pdfs)}")

        for pdf in pdfs:

            try:

                parsed = parser(pdf)

                save_json(
                    parsed,
                    output_year / f"{pdf.stem}.json"
                )

                print(f"Parsed : {pdf.name}")

            except Exception as e:

                print(f"Failed : {pdf.name}")

                print(e)


def main():

    for report_name, parser in REPORT_TYPES.items():

        process_report(
            report_name,
            parser
        )


if __name__ == "__main__":
    main()