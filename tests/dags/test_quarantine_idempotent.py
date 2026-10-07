"""Task 40 -- a scheduled parser re-reads every file each run; the same open rejection must not be inserted again (it was: 13 rows for one PDF)."""

import contextlib

import pipeline.utils.quarantine as Q


class Conn:
    def __init__(self):
        self.calls = []

    def execute(self, stmt, params):
        self.calls.append((str(stmt), params))


class Engine:
    def __init__(self):
        self.conn = Conn()

    @contextlib.contextmanager
    def begin(self):
        yield self.conn


def test_insert_is_guarded_by_an_identical_open_row_check(monkeypatch):
    eng = Engine()
    monkeypatch.setattr(Q, "engine", eng)
    assert Q.write_quarantine("ndma", "sitrep", "data/rejected/ndma/x.pdf", "schema_invalid", "m", "1.0.0") is True
    sql, params = eng.conn.calls[0]
    assert "WHERE NOT EXISTS" in sql
    for col in ("source", "domain", "source_document", "reason_code", "parser_version", "raw_payload"):
        assert f"q.{col}" in sql
    assert "q.status = 'open'" in sql and "IS NOT DISTINCT FROM" in sql
    assert params["source_document"] == "data/rejected/ndma/x.pdf" and params["raw_payload"] is None


def test_a_database_failure_is_still_logged_not_raised(monkeypatch):
    class Boom:
        def begin(self):
            raise RuntimeError("db down")
    monkeypatch.setattr(Q, "engine", Boom())
    assert Q.write_quarantine("pmd", "daily_forecast", "d", "row_too_short", "m", "1.0.0", raw_payload={"a": 1}) is False
