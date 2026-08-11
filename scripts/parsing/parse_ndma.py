import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==========================================================
# VALIDATION
# ==========================================================

from validation.ndma.schema import validate_schema
from validation.ndma.completeness import calculate_completeness
from validation.ndma.score import calculate_score

# ==========================================================
# COMMON
# ==========================================================

from common.pdf_reader import (
    extract_pdf_text,
    get_pdf_page_count,
)

from common.pdf_table_reader import extract_tables
from common.ndma_table_parser import parse_tables
from common.text_cleaner import clean_text
from common.parser_utils import save_json

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

REJECTED_FOLDER = Path(
    "data/rejected/ndma"
)
# ==========================================================
# PARSE PDF
# ==========================================================

def parse_pdf(pdf_file: Path):

    print(f"\nParsing : {pdf_file.name}")

    # ------------------------------------------------------
    # Extract Text
    # ------------------------------------------------------

    text = extract_pdf_text(pdf_file)
    text = clean_text(text)

    # ------------------------------------------------------
    # Extract Tables
    # ------------------------------------------------------

    tables = extract_tables(pdf_file)

    structured_tables = parse_tables(tables)

    # ------------------------------------------------------
    # Schema Validation
    # ------------------------------------------------------

    valid, errors = validate_schema(structured_tables)

    if not valid:

        print("=" * 60)
        print("NDMA VALIDATION FAILED")
        print("=" * 60)

        for err in errors:
            print(f"- {err}")

        print("=" * 60)

        REJECTED_FOLDER.mkdir(
            parents=True,
            exist_ok=True,
        )

        copy2(
            pdf_file,
            REJECTED_FOLDER / pdf_file.name,
        )

        print(f"Rejected -> {pdf_file.name}")

        return {
            "success": False,
            "quality": 0,
            "completeness": 0,
            "errors": errors,
        }
    # ------------------------------------------------------
    # Build Parsed Data
    # ------------------------------------------------------

    data = {

        "source": "NDMA",

        "report_type": "sitrep",

        "filename": pdf_file.name,

        "pages": get_pdf_page_count(pdf_file),

        "parsed_at": datetime.now().isoformat(),

        "report_number": extract_report_number(text),

        "report_date": extract_report_date(text),

        "subject": extract_subject(text),

        "raw_text": text,

        "casualties": structured_tables["casualties"],

        "damage": structured_tables["damage"],

        "relief": structured_tables["relief"],

        "rescue": structured_tables["rescue"],

        "provinces": extract_provinces(text),

        "rivers": extract_rivers(text),

        "dams": extract_dams(text),

        "weather_events": extract_weather_events(text),

    }
# ======================================================
# COMPLETENESS
# ======================================================

    completeness = calculate_completeness(data)

# ======================================================
# QUALITY SCORE
# ======================================================

    quality = calculate_score(
        data,
        errors
    )

# ======================================================
# VALIDATION REPORT
# ======================================================

    data["validation"] = {

        "schema_valid": True,

        "completeness": quality["completeness"],

        "quality_score": quality["score"],

        "quality_level": quality["quality"],

        "error_count": quality["error_count"],

        "penalty": quality["penalty"],

        "valid": quality["valid"],

        "errors": quality["errors"]

    }

# ======================================================
# QUALITY CHECK
# ======================================================

    if not quality["valid"]:

        print("=" * 60)
        print("NDMA QUALITY CHECK FAILED")
        print("=" * 60)

        print(f"Quality Score : {quality['score']}")
        print(f"Completeness  : {quality['completeness']}")
        print(f"Quality Level : {quality['quality']}")

        if quality["errors"]:

            print("\nErrors:")

            for err in quality["errors"]:
                print(f"- {err}")

        print("=" * 60)

        REJECTED_FOLDER.mkdir(
            parents=True,
            exist_ok=True,
        )

        copy2(
            pdf_file,
            REJECTED_FOLDER / pdf_file.name,
        )

        print(f"Rejected -> {pdf_file.name}")

        return {
            "success": False
        }

# ======================================================
# SAVE JSON
# ======================================================

    output_file = OUTPUT_FOLDER / f"{pdf_file.stem}.json"

    save_json(
        data,
        output_file,
    )

    print(f"Saved : {output_file.name}")

    print(f"Completeness : {quality['completeness']}%")

    print(f"Quality Score : {quality['score']}/100")

    print(f"Quality Level : {quality['quality']}")

    return {

        "success": True,

        "quality": quality["score"],

        "completeness": quality["completeness"]

    }

# ==========================================================
# MAIN
# ==========================================================

def main():

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    REJECTED_FOLDER.mkdir(
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

    parsed = 0
    rejected = 0

    quality_scores = []
    completeness_scores = []

    for pdf in pdf_files:

        result = parse_pdf(pdf)

        if result["success"]:

            parsed += 1

            quality_scores.append(
                result["quality"]
            )

            completeness_scores.append(
                result["completeness"]
            )

        else:

            rejected += 1

    print()
    print("=" * 70)
    print("NDMA PARSING SUMMARY")
    print("=" * 70)

    print(f"Total PDFs           : {len(pdf_files)}")
    print(f"Successfully Parsed  : {parsed}")
    print(f"Rejected             : {rejected}")

    success_rate = round(
        (parsed / len(pdf_files)) * 100,
        2,
    )

    print(f"Success Rate         : {success_rate}%")

    if quality_scores:

        avg_quality = round(

            sum(quality_scores) /
            len(quality_scores),

            2

        )

        avg_completeness = round(

            sum(completeness_scores) /
            len(completeness_scores),

            2

        )

        print(f"Average Quality      : {avg_quality}")

        print(f"Average Completeness : {avg_completeness}%")

    print("=" * 70)
    print("NDMA PARSING COMPLETED")
    print("=" * 70)



# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    main()