from pathlib import Path

from common.pdf_table_reader import extract_tables

PDF = Path(
    "data/raw/ndma/reports/sitreps/all/pdfs/6a439f4f1e083.pdf"
)

tables = extract_tables(PDF)

print("=" * 60)
print("Tables Found :", len(tables))
print("=" * 60)

for i, table in enumerate(tables):

    print(f"\nTABLE {i+1}")

    for row in table[:5]:
        print(row)