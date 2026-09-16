"""Deterministic canonical JSONL writer; never touches source-parser output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def write_jsonl(records: Iterable[dict], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda item: (item.get("source", ""), item.get("source_record_id", "")))
    payload = "".join(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n" for record in ordered)
    output_path.write_text(payload, encoding="utf-8")
    return output_path
