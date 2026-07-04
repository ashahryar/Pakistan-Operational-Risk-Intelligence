"""
pdf_reader.py

Reusable PDF reader.
"""

from pathlib import Path

import fitz


def extract_pdf_text(pdf_path: Path) -> str:
    """
    Extract all text from PDF.
    """

    document = fitz.open(pdf_path)

    pages = []

    for page in document:
        pages.append(page.get_text("text"))

    document.close()

    return "\n".join(pages)


def extract_pdf_pages(pdf_path: Path) -> list[str]:
    """
    Return page-wise text.
    """

    document = fitz.open(pdf_path)

    pages = []

    for page in document:
        pages.append(page.get_text("text"))

    document.close()

    return pages


def get_pdf_page_count(pdf_path: Path) -> int:
    """
    Return total page count.
    """

    document = fitz.open(pdf_path)

    count = len(document)

    document.close()

    return count