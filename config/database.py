import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Docker ya Local automatically detect
if os.path.exists("/.dockerenv"):
    DB_HOST = "postgres"
    DB_PORT = "5432"
else:
    DB_HOST = "localhost"
    DB_PORT = "5433"

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL, echo=False)


def get_connection():
    return engine.connect()


def get_engine():
    return engine

print("=" * 60)
print("DATABASE URL")
print(DATABASE_URL)
print("=" * 60)