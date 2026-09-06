"""
scripts/database/create_dq_tables.py

Phase 1 / Task 5 (ADR-0001) — DDL only. Creates the `dq` schema and the
`dq.quarantine` table used by pipeline/utils/quarantine.py.

Per CLAUDE.md rule 2, this must NOT be run against the live database
without a fresh, restore-verified pg_dump taken first. It is a one-off,
hand-run script (not wired into any DAG) — Alembic becomes the only
schema-change mechanism once Phase 1 lands (CLAUDE.md rule 4); Phase 1
itself is still in progress, so a single hand-run DDL script is
consistent with the current rules.

Run manually:
    python scripts/database/create_dq_tables.py
"""

from sqlalchemy import text

from config.database import engine


DDL_STATEMENTS = [

    "CREATE SCHEMA IF NOT EXISTS dq;",

    """
    CREATE TABLE IF NOT EXISTS dq.quarantine (
        quarantine_id   BIGSERIAL PRIMARY KEY,
        source          TEXT NOT NULL,
        domain          TEXT,
        source_document TEXT NOT NULL,
        raw_payload     JSONB,
        reason_code     TEXT NOT NULL,
        message         TEXT,
        parser_version  TEXT NOT NULL,
        quarantined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        status          TEXT NOT NULL DEFAULT 'open'
    );
    """,

    "CREATE INDEX IF NOT EXISTS ix_quarantine_source_time ON dq.quarantine (source, quarantined_at);",

    "CREATE INDEX IF NOT EXISTS ix_quarantine_status ON dq.quarantine (status);",

]


def main():

    print("=" * 60)
    print("CREATE DQ TABLES")
    print("=" * 60)

    with engine.begin() as conn:

        for stmt in DDL_STATEMENTS:
            conn.execute(text(stmt))

    print("dq.quarantine ready.")
    print("=" * 60)


if __name__ == "__main__":

    main()
