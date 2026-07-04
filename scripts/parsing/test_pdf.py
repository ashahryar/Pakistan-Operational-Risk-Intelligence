"""
Test PDF Reader

Usage:
python scripts/parsing/test_pdf.py
"""

from pathlib import Path

from common.pdf_reader import (
    extract_pdf_text,
    extract_pdf_pages,
    get_pdf_page_count,
)

PDF_FILE = Path(
    "data/raw/ndma/reports/sitreps/all/pdfs/6a439f4f1e083.pdf"
)


def main():

    if not PDF_FILE.exists():
        print(f"PDF not found: {PDF_FILE}")
        return

    print("=" * 70)
    print("PDF READER TEST")
    print("=" * 70)

    print(f"File      : {PDF_FILE.name}")
    print(f"Pages     : {get_pdf_page_count(PDF_FILE)}")

    pages = extract_pdf_pages(PDF_FILE)

    print(f"Text Pages: {len(pages)}")

    text = extract_pdf_text(PDF_FILE)

    print(f"Characters: {len(text)}")

    print("\nFIRST 1000 CHARACTERS\n")
    print("-" * 70)
    print(text[:1000])
    print("-" * 70)

    print("\nPDF Reader Working Successfully")


if __name__ == "__main__":
    main()