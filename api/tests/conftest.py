import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

PERMISSIVE = {"lexical": {"min_coverage": 0.0}, "semantic": {"min_cosine": 0.0}, "hybrid": {"min_coverage": 0.0, "rule": "or"}}


@pytest.fixture(autouse=True)
def relevance_policy(request, monkeypatch):
    """The API / agent tests use tiny fake corpora to check contracts, not relevance, so the relevance gate is made permissive for them (every returned chunk passes).
    Tests marked `strict_relevance` run with the REAL policy (api/tests/test_rag_relevance_api.py and the real-data tests)."""
    if request.node.get_closest_marker("strict_relevance") is None:
        import pipeline.rag.relevance as rel
        monkeypatch.setattr(rel, "POLICY", PERMISSIVE)
    yield
