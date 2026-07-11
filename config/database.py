import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

env_path = Path(__file__).resolve().parents[1] / ".env"

load_dotenv(env_path, override=True)

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
)

def get_connection():
    return engine.connect()

def get_engine():
    return engine