"""
Extract tables from PDF.
"""

from pathlib import Path

import pdfplumber


def extract_tables(pdf_file: Path):

    tables = []

    with pdfplumber.open(pdf_file) as pdf:

        for page in pdf.pages:

            page_tables = page.extract_tables()

            if page_tables:

                tables.extend(page_tables)

    return tables   