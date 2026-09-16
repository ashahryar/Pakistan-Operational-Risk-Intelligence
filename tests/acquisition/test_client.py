"""
tests/acquisition/test_client.py

Phase 1 / Task 15 (ADR-0001) -- deterministic tests for
scripts/acquisition/client.py's validation logic. The HTTP layer
itself is monkeypatched (`scripts.acquisition.client._session.get`) so
these tests make zero real network calls -- fully deterministic, no
internet dependency, matching the project's established test
convention (Tasks 5-14 all avoid live network/DB in pytest).
"""

from __future__ import annotations

import requests

from scripts.acquisition import client as client_module
from scripts.acquisition.client import fetch, fetch_binary, fetch_json


class _FakeResponse:
    def __init__(self, status_code, content, content_type):
        self.status_code = status_code
        self.content = content
        self.headers = {"Content-Type": content_type} if content_type else {}


def _patch_get(monkeypatch, response=None, raise_exc=None):
    def fake_get(url, timeout, headers=None):
        if raise_exc is not None:
            raise raise_exc
        return response

    monkeypatch.setattr(client_module._session, "get", fake_get)


def test_fetch_rejects_non_2xx_status(monkeypatch):
    _patch_get(monkeypatch, response=_FakeResponse(404, b"not found", "text/plain"))
    result = fetch("https://example.gov.pk/missing")
    assert result.ok is False
    assert result.error_code == "http_error"
    assert result.http_status == 404


def test_fetch_rejects_empty_response(monkeypatch):
    _patch_get(monkeypatch, response=_FakeResponse(200, b"", "application/json"))
    result = fetch("https://example.gov.pk/empty")
    assert result.ok is False
    assert result.error_code == "empty_response"


def test_fetch_accepts_a_normal_2xx_response(monkeypatch):
    _patch_get(monkeypatch, response=_FakeResponse(200, b"hello", "text/plain"))
    result = fetch("https://example.gov.pk/ok")
    assert result.ok is True
    assert result.content == b"hello"
    assert result.byte_size == 5


def test_fetch_captures_connection_error(monkeypatch):
    _patch_get(monkeypatch, raise_exc=requests.ConnectionError("boom"))
    # Avoid the real retry sleep slowing the test suite.
    import time as _time
    real_sleep = _time.sleep
    _time.sleep = lambda *_: None
    try:
        result = fetch("https://example.gov.pk/down")
    finally:
        _time.sleep = real_sleep
    assert result.ok is False
    assert result.error_code == "connection_error"
    assert result.http_status is None


def test_fetch_json_accepts_real_json(monkeypatch):
    _patch_get(monkeypatch, response=_FakeResponse(200, b'{"a": 1}', "application/json"))
    result = fetch_json("https://example.gov.pk/api")
    assert result.ok is True
    assert result.parsed_json == {"a": 1}


def test_fetch_json_rejects_html_error_page(monkeypatch):
    html = b"<!DOCTYPE html><html><body>404 Not Found</body></html>"
    _patch_get(monkeypatch, response=_FakeResponse(200, html, "text/html"))
    result = fetch_json("https://example.gov.pk/api")
    assert result.ok is False
    assert result.error_code == "unexpected_html"


def test_fetch_json_rejects_malformed_json(monkeypatch):
    _patch_get(monkeypatch, response=_FakeResponse(200, b"{not valid json", "application/json"))
    result = fetch_json("https://example.gov.pk/api")
    assert result.ok is False
    assert result.error_code == "invalid_json"


def test_fetch_binary_accepts_matching_content_type(monkeypatch):
    _patch_get(monkeypatch, response=_FakeResponse(200, b"%PDF-1.4 fake pdf bytes", "application/pdf"))
    result = fetch_binary("https://example.gov.pk/report.pdf", expected_content_type_prefixes=("application/pdf",))
    assert result.ok is True


def test_fetch_binary_rejects_content_type_mismatch(monkeypatch):
    # A PDF link that actually serves an HTML error page with a 200 status --
    # a real failure mode of CMS-hosted government sites.
    _patch_get(monkeypatch, response=_FakeResponse(200, b"<html>oops</html>", "text/html"))
    result = fetch_binary("https://example.gov.pk/report.pdf", expected_content_type_prefixes=("application/pdf",))
    assert result.ok is False
    assert result.error_code == "content_type_mismatch"
