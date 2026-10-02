"""Versioned risk-engine configuration loader (config/risk_engine.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "risk_engine.yaml"
REQUIRED_KEYS = ("engine_version", "calculation_version", "enabled_domains", "normalization",
                 "provisional_status_cutpoints", "score", "confidence")


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load((path or DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ValueError(f"risk config missing required keys: {missing}")
    return cfg


def enabled_geographic_domains(cfg: dict[str, Any]) -> list[str]:
    return [d for d, on in cfg["enabled_domains"].items() if on and d != "documents"]
