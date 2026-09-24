"""Guard: tests in this package must never write to the real dq.quarantine table.

Canonical adapters fall back to `pipeline.utils.quarantine.write_quarantine` (a real database
insert) when no `quarantine=` sink is passed. This fixture makes any such accidental call fail
loudly instead of silently polluting the database.
"""

import pytest


@pytest.fixture(autouse=True)
def _forbid_real_quarantine_writes(monkeypatch):
    def _refuse(**kwargs):
        raise AssertionError(f"test attempted a real dq.quarantine write: {kwargs.get('reason_code')}")

    monkeypatch.setattr("pipeline.utils.quarantine.write_quarantine", _refuse)
