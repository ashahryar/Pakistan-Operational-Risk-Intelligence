import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import text
from config.database import engine


with engine.connect() as conn:

    version = conn.execute(
        text("SELECT version();")
    ).scalar()

    print("=" * 60)
    print("CONNECTED SUCCESSFULLY")
    print("=" * 60)
    print(version)