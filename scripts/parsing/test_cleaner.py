from pathlib import Path

from common.pdf_reader import extract_pdf_text
from common.text_cleaner import clean_text

PDF = Path(
    "data/raw/ndma/reports/sitreps/all/pdfs/6a439f4f1e083.pdf"
)

raw = extract_pdf_text(PDF)

clean = clean_text(raw)

print("=" * 70)
print("RAW TEXT")
print("=" * 70)

print(raw[:1000])

print("\n")

print("=" * 70)
print("CLEANED TEXT")
print("=" * 70)

print(clean[:1000])