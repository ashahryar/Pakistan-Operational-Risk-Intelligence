from sqlalchemy import create_engine

DB_USER = "postgres"
DB_PASSWORD = "123456789"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "pakistan_operational_risk"

DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
)