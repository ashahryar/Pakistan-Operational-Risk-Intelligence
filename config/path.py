from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DATA = BASE_DIR / "data" / "raw"

PROCESSED_DATA = BASE_DIR / "data" / "processed"

CURATED_DATA = BASE_DIR / "data" / "curated"