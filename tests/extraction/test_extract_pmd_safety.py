"""
tests/extraction/test_extract_pmd_safety.py

Task 16A (Phase 1 / ADR-0001), Part A item 6 -- extract_pmd.py
(confirmed active, DAG-referenced) previously wrote its scraped
`latest.json` via a direct `open(...,"w")`, with no atomic-write or
checksum-verification discipline. It now reuses Task 15's
scripts/acquisition/raw_store.write_verified_bytes() for that write.

Isolation note: scripts/extraction/common/ and scripts/parsing/common/
are two DIFFERENT top-level packages both literally named `common`,
disambiguated only by which directory is on sys.path first at import
time -- a pre-existing repo characteristic, not something this task
changes. Importing extract_pmd (which does `from common.fetcher import
...`, expecting scripts/extraction on sys.path) would otherwise poison
sys.modules['common'] for the rest of the pytest session, breaking any
later-collected test that needs scripts/parsing/common/ instead (e.g.
tests/parsers/test_ndma_golden.py's `from common.pdf_reader import
...`). The fixture below imports extract_pmd inside an isolated
sys.path/sys.modules sandbox and fully restores both afterward.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTRACTION_DIR = PROJECT_ROOT / "scripts" / "extraction"


@pytest.fixture
def extract_pmd_module():
    """Imports extract_pmd with scripts/extraction on sys.path, then
    restores sys.path and purges every `common`/`common.*` entry this
    import added to sys.modules, so later test files resolving a
    different `common` package (scripts/parsing/common/) are
    unaffected."""
    original_path = list(sys.path)
    original_modules = dict(sys.modules)

    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(EXTRACTION_DIR))

    # Drop any already-cached `common`/`extract_pmd` from an earlier
    # (differently-rooted) import so this import resolves fresh
    # against scripts/extraction/common/.
    for name in list(sys.modules):
        if name == "common" or name.startswith("common.") or name == "extract_pmd":
            del sys.modules[name]

    import extract_pmd

    try:
        yield extract_pmd
    finally:
        sys.path[:] = original_path
        for name in list(sys.modules):
            if name not in original_modules:
                del sys.modules[name]
        sys.modules.update(original_modules)


def test_extract_pmd_source_no_longer_opens_the_output_file_directly():
    source = (EXTRACTION_DIR / "extract_pmd.py").read_text(encoding="utf-8")
    assert 'open(json_file, "w"' not in source
    assert "write_verified_bytes" in source


def test_extract_pmd_uses_the_real_write_verified_bytes_function(extract_pmd_module):
    assert extract_pmd_module.write_verified_bytes.__module__ == "scripts.acquisition.raw_store"


def test_scrape_report_writes_a_real_verifiable_json_file(monkeypatch, tmp_path, extract_pmd_module):
    extract_pmd = extract_pmd_module

    class FakeResponse:
        status_code = 200
        text = "<html><body>forecast text here</body></html>"

    monkeypatch.setattr(extract_pmd.client, "get", lambda url: FakeResponse())
    monkeypatch.setattr(extract_pmd, "extract_forecast_text", lambda soup: "Sunny")
    monkeypatch.setattr(extract_pmd, "extract_tables", lambda soup: [{"city": "Lahore"}])
    monkeypatch.setattr(extract_pmd, "get_report_directory", lambda *a, **k: tmp_path)

    result = extract_pmd.scrape_report("daily_forecast", extract_pmd.REPORTS["daily_forecast"])

    assert result == 1
    written = tmp_path / "latest.json"
    assert written.exists()
    assert b"forecast" in written.read_bytes()
