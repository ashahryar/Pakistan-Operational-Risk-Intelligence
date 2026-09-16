"""
scripts/acquisition/raw_store.py

Phase 1 / Task 15 (ADR-0001) -- immutable raw-artifact storage.

Layout (extends the project's existing data/raw/<source>/... convention
rather than replacing it -- scripts/extraction/common/filesystem.py's
`data/raw/<source>/reports/<type>/<year>/pdfs/` pattern is left
untouched for the existing NDMA/PDMA/PMD scrapers; this is a sibling
convention for the new Tier 1 sources):

    data/raw/<organization>/<dataset>/<retrieval_date>/<filename>

An artifact, once written, is never silently overwritten. Saving the
exact same bytes again is recorded as a duplicate retrieval (the
existing file is left untouched, nothing is rewritten). Saving
*different* bytes under a name that already exists on disk is treated
as a new retrieval and is given a disambiguating suffix so the
original is never destroyed -- CLAUDE.md rule 1 ("never destroy
historical raw evidence") applies here exactly as it does to the
existing scrapers.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config.path import RAW_DATA


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    """
    A transient `OSError: [Errno 22] Invalid argument` has been observed
    on Windows immediately after another process (e.g. antivirus)
    touches a just-written file -- the same class of Windows-specific
    filesystem flakiness CLAUDE.md's gotcha table already documents for
    this project. Two attempts with a brief pause is enough to ride out
    the transient case without masking a genuine, persistent I/O error.
    """
    last_error = None
    for attempt in range(4):
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except OSError as e:
            last_error = e
            time.sleep(0.3 * (attempt + 1))
    raise last_error


@dataclass
class SavedArtifact:
    organization: str
    dataset: str
    local_path: Path
    filename: str
    sha256: str
    byte_size: int
    is_duplicate: bool  # True if identical content already existed on disk


def artifact_directory(organization: str, dataset: str, retrieved_at: datetime, base_dir: Path = RAW_DATA) -> Path:
    retrieval_date = retrieved_at.date() if isinstance(retrieved_at, datetime) else retrieved_at
    return base_dir / organization / dataset / retrieval_date.isoformat()


def save_raw_artifact(
    organization: str,
    dataset: str,
    retrieved_at: datetime,
    filename: str,
    content: bytes,
    base_dir: Path = RAW_DATA,
) -> SavedArtifact:
    """
    Writes `content` to
    data/raw/<organization>/<dataset>/<retrieved_at:%Y-%m-%d>/<filename>,
    creating parent directories as needed.

    Rejects zero-byte content outright (a zero-byte "download" is
    always a failure, never a valid artifact -- CLAUDE.md rule 7).

    If a file of the same name already exists:
      - identical content  -> returns the EXISTING artifact info with
        is_duplicate=True; nothing is written or touched.
      - different content   -> writes the new content under a
        disambiguated filename (a `__HHMMSS` suffix inserted before the
        extension, derived from `retrieved_at`), so both the original
        and the new retrieval survive on disk.
    """

    if not content:
        raise ValueError(f"refusing to save a zero-byte artifact: {organization}/{dataset}/{filename}")

    directory = artifact_directory(organization, dataset, retrieved_at, base_dir=base_dir)
    directory.mkdir(parents=True, exist_ok=True)

    target = directory / filename
    new_checksum = sha256_bytes(content)

    if target.exists():
        existing_checksum = sha256_file(target)
        if existing_checksum == new_checksum:
            return SavedArtifact(
                organization=organization,
                dataset=dataset,
                local_path=target,
                filename=target.name,
                sha256=existing_checksum,
                byte_size=target.stat().st_size,
                is_duplicate=True,
            )

        stem, _, ext = filename.rpartition(".")
        suffix = retrieved_at.strftime("%H%M%S") if isinstance(retrieved_at, datetime) else "000000"
        disambiguated = f"{stem or filename}__{suffix}" + (f".{ext}" if ext else "")
        target = directory / disambiguated
        # In the rare case the disambiguated name is also already taken
        # (e.g. two saves within the same second), append an incrementing
        # counter rather than ever overwriting.
        counter = 2
        while target.exists() and sha256_file(target) != new_checksum:
            target = directory / f"{stem or filename}__{suffix}_{counter}" + (f".{ext}" if ext else "")
            counter += 1
        if target.exists() and sha256_file(target) == new_checksum:
            return SavedArtifact(
                organization=organization, dataset=dataset, local_path=target,
                filename=target.name, sha256=new_checksum, byte_size=target.stat().st_size,
                is_duplicate=True,
            )

    persisted_checksum = _write_and_read_back(target, content)

    return SavedArtifact(
        organization=organization,
        dataset=dataset,
        local_path=target,
        filename=target.name,
        sha256=persisted_checksum,
        byte_size=target.stat().st_size,
        is_duplicate=False,
    )


def write_verified_bytes(target: Path, content: bytes, max_attempts: int = 25) -> str:
    """
    Public, path-and-convention-agnostic entry point onto the same
    write-then-verify-by-reading-back discipline `save_raw_artifact()`
    uses internally -- for callers (e.g. the legacy
    scripts/extraction/ extractors, Task 16A) that need atomic,
    checksum-verified writes but use a different directory convention
    than this module's own `data/raw/<organization>/<dataset>/<date>/`
    layout, so `save_raw_artifact()` itself doesn't fit. Creates
    `target`'s parent directory if needed. Raises OSError if the write
    can never be confirmed readable within `max_attempts` -- the same
    "never silently succeed on an unverifiable write" guarantee as the
    rest of this module. Raises ValueError on zero-byte content, same
    as save_raw_artifact() (CLAUDE.md rule 7 -- a zero-byte download is
    always a failure, never a valid artifact).
    """
    if not content:
        raise ValueError(f"refusing to write a zero-byte artifact: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return _write_and_read_back(target, content, max_attempts=max_attempts)


def _write_and_read_back(target: Path, content: bytes, max_attempts: int = 25) -> str:
    """
    Writes `content` to `target`, then reads it back and returns the
    checksum of what is ACTUALLY persisted on disk -- not the checksum
    of the in-memory `content` that was fetched over the network.

    This distinction matters: a real, reproducible interaction was
    found during Task 15's live acquisition runs where specific fetched
    HTML content, for a period after being written, is unreadable
    (`OSError: [Errno 22]`, confirmed independent of this module's code
    via a plain `cat` and a freshly-started Python process) and then
    -- once it does become readable -- sometimes hashes DIFFERENTLY
    from what was written, with identical file ACLs before and after.
    This is consistent with local endpoint-security content scanning/
    rewriting (not a bug in this module's write path, and not a bug in
    the source page -- ruled out by writing plain synthetic bytes
    through the exact same code path with no issue).

    Given that, the only checksum worth recording in the manifest is
    one computed from bytes actually read back off disk -- recording
    the pre-write in-memory hash would risk describing content that
    doesn't match what a later consumer of this raw artifact would
    actually read. If the file cannot be read back at all within
    `max_attempts` (generous backoff, ~115s total -- live testing on
    2026-09-16 showed one page taking up to ~90s to stabilize), this
    raises -- an acquisition whose artifact can't be confirmed to
    exist on disk in a readable state is not a successful acquisition.
    """

    with open(target, "wb") as f:
        f.write(content)
        f.flush()

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return sha256_file(target)
        except OSError as e:
            last_error = e
            time.sleep(min(1.0 * attempt, 5.0))

    raise OSError(
        f"could not read back {target} after writing it ({max_attempts} attempts): {last_error} -- "
        f"refusing to record an artifact that cannot be confirmed readable on disk"
    )
