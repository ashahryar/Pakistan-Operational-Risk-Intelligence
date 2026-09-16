"""
tests/acquisition/test_raw_store.py

Phase 1 / Task 15 (ADR-0001) -- deterministic tests for
scripts/acquisition/raw_store.py. Uses pytest's tmp_path fixture as
`base_dir` so nothing touches the real data/raw/ tree -- no live DB,
no network.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.acquisition.raw_store import (
    artifact_directory,
    save_raw_artifact,
    sha256_bytes,
    sha256_file,
)


def test_artifact_directory_layout(tmp_path):
    retrieved_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    directory = artifact_directory("suparco", "disasterwatch", retrieved_at, base_dir=tmp_path)
    assert directory == tmp_path / "suparco" / "disasterwatch" / "2026-09-16"


def test_save_raw_artifact_writes_file_and_returns_checksum(tmp_path):
    retrieved_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    content = b'{"hello": "world"}'

    artifact = save_raw_artifact(
        "suparco", "disasterwatch", retrieved_at, "global-themes.json", content, base_dir=tmp_path
    )

    assert artifact.local_path.exists()
    assert artifact.local_path.read_bytes() == content
    assert artifact.sha256 == sha256_bytes(content)
    assert artifact.byte_size == len(content)
    assert artifact.is_duplicate is False


def test_save_raw_artifact_rejects_zero_byte_content(tmp_path):
    retrieved_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        save_raw_artifact("suparco", "disasterwatch", retrieved_at, "empty.json", b"", base_dir=tmp_path)


def test_identical_content_saved_twice_is_marked_duplicate_and_not_rewritten(tmp_path):
    retrieved_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    content = b'{"a": 1}'

    first = save_raw_artifact("aqi", "punjab", retrieved_at, "districts.json", content, base_dir=tmp_path)
    mtime_after_first = first.local_path.stat().st_mtime

    second = save_raw_artifact("aqi", "punjab", retrieved_at, "districts.json", content, base_dir=tmp_path)

    assert second.is_duplicate is True
    assert second.local_path == first.local_path
    assert second.sha256 == first.sha256
    # The file must not have been rewritten -- same mtime.
    assert second.local_path.stat().st_mtime == mtime_after_first


def test_different_content_under_the_same_filename_never_overwrites_the_original(tmp_path):
    retrieved_at = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

    first = save_raw_artifact("aqi", "punjab", retrieved_at, "districts.json", b'{"v": 1}', base_dir=tmp_path)
    second = save_raw_artifact("aqi", "punjab", retrieved_at, "districts.json", b'{"v": 2}', base_dir=tmp_path)

    # Original file is untouched.
    assert first.local_path.exists()
    assert first.local_path.read_bytes() == b'{"v": 1}'

    # New content landed under a different, disambiguated path.
    assert second.local_path != first.local_path
    assert second.local_path.exists()
    assert second.local_path.read_bytes() == b'{"v": 2}'
    assert second.is_duplicate is False


def test_sha256_file_matches_sha256_bytes(tmp_path):
    content = b"some raw bytes"
    path = tmp_path / "f.bin"
    path.write_bytes(content)
    assert sha256_file(path) == sha256_bytes(content)
