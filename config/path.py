from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RAW_DATA = BASE_DIR / "data" / "raw"
PARSED_DATA = BASE_DIR / "data" / "parsed"
ANALYTICS_DATA = BASE_DIR / "data" / "analytics"