# """
# Extract tables from PDF.
# """

# from pathlib import Path

# import pdfplumber


# def extract_tables(pdf_file: Path):

#     tables = []

#     with pdfplumber.open(pdf_file) as pdf:

#         for page in pdf.pages:

#             page_tables = page.extract_tables()

#             if page_tables:

#                 tables.extend(page_tables)

#     return tables   

from pathlib import Path
import pdfplumber

def extract_tables(pdf_file: Path):

    tables = []

    with pdfplumber.open(pdf_file) as pdf:

        for page_no, page in enumerate(pdf.pages, start=1):

            page_tables = page.extract_tables()

            print(f"\n========== PAGE {page_no} ==========")
            print("Tables Found:", len(page_tables))

            for table_no, table in enumerate(page_tables, start=1):

                print(f"\nTABLE {table_no}")

                for row in table[:10]:
                    print(row)

            if page_tables:
                tables.extend(page_tables)

    return tables