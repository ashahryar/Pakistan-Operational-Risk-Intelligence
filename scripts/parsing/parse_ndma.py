from pathlib import Path
from datetime import datetime

from common.pdf_reader import (
    extract_pdf_text,
    get_pdf_page_count,
)
from common.pdf_table_reader import extract_tables

from common.ndma_table_parser import parse_tables

from common.text_cleaner import clean_text
from common.parser_utils import save_json

from common.ndma_parser import (
    extract_report_date,
    extract_report_number,
    extract_subject,
)
from common.ndma_information_extractor import (

    extract_report_number,

    extract_report_date,

    extract_subject,

    extract_provinces,

    extract_rivers,

    extract_dams,

    extract_weather_events,

)

# ==========================================================
# CONFIGURATION
# ==========================================================

INPUT_FOLDER = Path(
    "data/raw/ndma/reports/sitreps/all/pdfs"
)

OUTPUT_FOLDER = Path(
    "data/parsed/ndma/sitreps"
)

# ==========================================================
# PARSE SINGLE PDF
# ==========================================================

def parse_pdf(pdf_file: Path):

    print(f"Parsing : {pdf_file.name}")

    text = extract_pdf_text(pdf_file)

    text = clean_text(text)
    tables = extract_tables(pdf_file)
    structured_tables = parse_tables(tables)

    report_number = extract_report_number(text)

    report_date = extract_report_date(text)

    subject = extract_subject(text)

    data = {

        "source": "NDMA",

        "report_type": "sitrep",

        "filename": pdf_file.name,

        "pages": get_pdf_page_count(pdf_file),

        "parsed_at": datetime.now().isoformat(),

        "casualties": structured_tables["casualties"],

        "damage": structured_tables["damage"],

        "relief": structured_tables["relief"],

        "rescue": structured_tables["rescue"],

        "report_number": report_number,

        "report_date": report_date,

        "subject": subject,

        "raw_text": text,
        
        "report_number": extract_report_number(text),

        "report_date": extract_report_date(text),

        "subject": extract_subject(text),

        "provinces": extract_provinces(text),

        "rivers": extract_rivers(text),

        "dams": extract_dams(text),

        "weather_events": extract_weather_events(text),

    }

    output_file = OUTPUT_FOLDER / f"{pdf_file.stem}.json"

    save_json(
        data,
        output_file,
    )

    print(f"Saved : {output_file.name}")

    


# ==========================================================
# MAIN
# ==========================================================

def main():

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    pdf_files = sorted(
        INPUT_FOLDER.glob("*.pdf")
    )

    if not pdf_files:

        print("No PDFs Found")

        return

    print("=" * 70)
    print(f"Found {len(pdf_files)} PDFs")
    print("=" * 70)

    count = 0

    for pdf in pdf_files:

        parse_pdf(pdf)

        count += 1

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total PDFs Parsed : {count}")
    print("=" * 70)


if __name__ == "__main__":
    main()