"""Read-only access to Task 15 raw artifacts and their manifests.

Files are matched to manifest records by sha256 (never by the manifest's Windows-absolute
`local_path`), so this works identically on the host and in a container. Nothing here writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = PROJECT_ROOT / "data" / "raw"
MANIFEST_DIR = RAW_ROOT / "manifests"


@dataclass(frozen=True)
class Artifact:
    path: Path
    sha256: str
    source_url: str | None
    retrieved_at: str | None
    dataset: str
    source_organization: str

    @property
    def filename(self) -> str:
        return self.path.name

    @property
    def relative_path(self) -> str:
        try:
            return self.path.resolve().relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    def provenance(self) -> dict:
        return {"source_file": self.relative_path, "source_url": self.source_url,
                "retrieved_at": self.retrieved_at, "sha256": self.sha256}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest_index(manifest_path: Path) -> dict[str, dict]:
    """sha256 -> earliest manifest record (deterministic: ties broken by retrieved_at, then url)."""
    index: dict[str, dict] = {}
    if not manifest_path.exists():
        return index
    with open(manifest_path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            key = record.get("sha256")
            if not key:
                continue
            best = index.get(key)
            if best is None or (record.get("retrieved_at") or "", record.get("source_url") or "") < (
                    best.get("retrieved_at") or "", best.get("source_url") or ""):
                index[key] = record
    return index


def discover_artifacts(dataset_dir: Path, manifest_path: Path, dataset: str, source_organization: str,
                       suffixes: tuple[str, ...] | None = None) -> list[Artifact]:
    """All raw files under `dataset_dir` (sorted), each joined to its manifest record by sha256."""
    index = load_manifest_index(manifest_path)
    artifacts = []
    for path in sorted(p for p in dataset_dir.rglob("*") if p.is_file()):
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        digest = sha256_file(path)
        record = index.get(digest, {})
        artifacts.append(Artifact(path, digest, record.get("source_url"), record.get("retrieved_at"),
                                  dataset, source_organization))
    return artifacts


def failure(reason_code: str, message: str, artifact: Artifact | None = None, raw_payload=None) -> dict:
    return {"reason_code": reason_code, "message": message,
            "source_document": artifact.relative_path if artifact else None, "raw_payload": raw_payload}
