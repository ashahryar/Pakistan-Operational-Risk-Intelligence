import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("config.database")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

_CREDENTIAL_RE = re.compile(r"(://[^:/@\s]+:)([^@\s]+)(@)")


def redact_credentials(text: str) -> str:
    """
    Replaces any embedded `user:password@` credential segment in a
    string (a connection URL, or an exception message that happens to
    include one) with `user:***REDACTED***@`. Safe to call on any
    string, including ones with no credentials in them (returned
    unchanged). Never logs, prints, or returns the real password.
    """
    if not text:
        return text
    return _CREDENTIAL_RE.sub(r"\1***REDACTED***\3", str(text))

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


logger.info("Database engine configured for %s", redact_credentials(DATABASE_URL))