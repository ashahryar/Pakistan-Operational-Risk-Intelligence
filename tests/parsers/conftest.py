"""
tests/parsers/conftest.py

Phase 1 / Task 8 (ADR-0001) — shared setup for parser golden-file and
type-coercion tests.

scripts/parsing/parse_ndma.py (and, transitively, nothing else we test
directly) imports from a bare `common` package
(`from common.pdf_reader import ...`, etc.) that actually lives at
scripts/parsing/common/. That import only resolves today because, when
the script is run standalone (`python scripts/parsing/parse_ndma.py`),
Python auto-inserts the script's own directory at the front of
sys.path. A pytest test file importing `scripts.parsing.parse_ndma` as
a module does not get that automatic insertion, so without the line
below the import fails with `ModuleNotFoundError: No module named
'common.pdf_reader'` (there IS an unrelated top-level `common/`
package at the repo root, containing only logger.py, which makes the
failure mode a confusing "module has no attribute" rather than a
clean "not found").

This is a test-side-only accommodation -- it does not touch
scripts/parsing/parse_ndma.py or change its behavior in any way, it
just mirrors what already happens when the script runs standalone
under pipeline/helpers/script_runner.py.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_PARSING_DIR = PROJECT_ROOT / "scripts" / "parsing"

for _p in (str(PROJECT_ROOT), str(SCRIPTS_PARSING_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
