"""
tests/extraction/test_downloader_safety.py

Task 16A (Phase 1 / ADR-0001), Part A item 6 -- hardening the active
legacy extractors (extract_ndma.py, extract_pdma.py -- confirmed
DAG-referenced by the Task 16 audit) to the minimum Task-15
acquisition safety standard, by reusing Task 15's own
client.fetch_binary()/raw_store.write_verified_bytes() inside
scripts/extraction/common/downloader.py::download_file() rather than
building a second acquisition framework.

These tests exercise the real download_file() against a monkeypatched
fetch_binary() (no live network) and a real tmp_path (real atomic
write/checksum verification, no mocking of raw_store).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.extraction.common.downloader as downloader  # noqa: E402
from scripts.acquisition.client import FetchResult  # noqa: E402

REAL_PDF_BYTES = b"%PDF-1.4\n%fake but starts with the real magic bytes\n"


def _ok_result(content: bytes, content_type: str = "application/pdf") -> FetchResult:
    return FetchResult(
        url="https://example.gov.pk/report.pdf",
        ok=True,
        http_status=200,
        content_type=content_type,
        content=content,
        byte_size=len(content),
        retrieved_at=datetime.now(timezone.utc),
    )


def _failed_result(error_code: str) -> FetchResult:
    return FetchResult(
        url="https://example.gov.pk/report.pdf",
        ok=False,
        http_status=404 if error_code == "http_error" else None,
        content_type=None,
        content=None,
        byte_size=0,
        retrieved_at=datetime.now(timezone.utc),
        error_code=error_code,
        error_message="simulated failure",
    )


def test_download_file_succeeds_for_a_real_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "fetch_binary", lambda url, expected_content_type_prefixes=(): _ok_result(REAL_PDF_BYTES))

    output = tmp_path / "report.pdf"
    ok = downloader.download_file("https://example.gov.pk/report.pdf", output)

    assert ok is True
    assert output.exists()
    assert output.read_bytes() == REAL_PDF_BYTES


def test_download_file_returns_false_on_http_error(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "fetch_binary", lambda url, expected_content_type_prefixes=(): _failed_result("http_error"))

    output = tmp_path / "report.pdf"
    ok = downloader.download_file("https://example.gov.pk/missing.pdf", output)

    assert ok is False
    assert not output.exists()


def test_download_file_returns_false_on_empty_response(monkeypatch, tmp_path):
    monkeypatch.setattr(downloader, "fetch_binary", lambda url, expected_content_type_prefixes=(): _failed_result("empty_response"))

    output = tmp_path / "report.pdf"
    ok = downloader.download_file("https://example.gov.pk/empty.pdf", output)

    assert ok is False
    assert not output.exists()


def test_download_file_rejects_an_html_error_page_served_as_a_pdf(monkeypatch, tmp_path):
    """
    The real failure mode this hardening targets: a WordPress/CMS site
    returns HTTP 200 with an HTML error page instead of the requested
    PDF, sometimes even with Content-Type: application/pdf. The magic-
    byte check must catch this even when the Content-Type header lies.
    """
    html_error_page = b"<html><body>404 Not Found</body></html>"
    monkeypatch.setattr(
        downloader, "fetch_binary",
        lambda url, expected_content_type_prefixes=(): _ok_result(html_error_page, content_type="application/pdf"),
    )

    output = tmp_path / "report.pdf"
    ok = downloader.download_file("https://example.gov.pk/report.pdf", output)

    assert ok is False
    assert not output.exists()


def test_download_file_rejects_content_type_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        downloader, "fetch_binary",
        lambda url, expected_content_type_prefixes=(): _failed_result("content_type_mismatch"),
    )

    output = tmp_path / "report.pdf"
    ok = downloader.download_file("https://example.gov.pk/report.pdf", output)

    assert ok is False
    assert not output.exists()


def test_download_file_passes_the_right_content_type_expectation_for_pdf(monkeypatch, tmp_path):
    captured = {}

    def fake_fetch_binary(url, expected_content_type_prefixes=()):
        captured["prefixes"] = expected_content_type_prefixes
        return _ok_result(REAL_PDF_BYTES)

    monkeypatch.setattr(downloader, "fetch_binary", fake_fetch_binary)

    downloader.download_file("https://example.gov.pk/report.pdf", tmp_path / "report.pdf")

    assert captured["prefixes"] == ("application/pdf",)


def test_download_file_never_leaves_a_partial_file_on_write_failure(monkeypatch, tmp_path):
    """write_verified_bytes raising must not leave a corrupted file
    mistaken for a successful download."""
    monkeypatch.setattr(downloader, "fetch_binary", lambda url, expected_content_type_prefixes=(): _ok_result(REAL_PDF_BYTES))

    def raising_write(target, content):
        raise OSError("simulated unverifiable write")

    monkeypatch.setattr(downloader, "write_verified_bytes", raising_write)

    output = tmp_path / "report.pdf"
    ok = downloader.download_file("https://example.gov.pk/report.pdf", output)

    assert ok is False
