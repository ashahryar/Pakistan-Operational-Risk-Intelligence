from sqlalchemy import text

from connection import engine


with engine.connect() as conn:

    version = conn.execute(
        text("SELECT version();")
    ).scalar()

    print("=" * 60)
    print("CONNECTED SUCCESSFULLY")
    print("=" * 60)
    print(version)