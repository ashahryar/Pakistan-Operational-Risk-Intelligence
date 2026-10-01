"""Task 22 -- feature registry consistency + real-data fixture checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.ml.feature_registry import FEATURE_REGISTRY
from pipeline.ml.features import GAUGE_FEATURE_COLUMNS, build_gauge_features

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_registered_gauge_feature_name_is_documented():
    documented = {name.split(".", 1)[1] for name in FEATURE_REGISTRY if name.startswith("gauge.")
                 and not name.startswith("gauge.target")}
    implemented = set(GAUGE_FEATURE_COLUMNS) | {"station_resolution_status", "observation_count"}
    assert documented == implemented


def test_every_feature_spec_has_a_non_empty_leakage_rule():
    for name, spec in FEATURE_REGISTRY.items():
        assert spec.leakage_rule, f"{name} has no documented leakage rule"


def test_gauge_targets_are_registered_as_targets_not_features():
    for horizon in ("t_plus_1", "t_plus_3", "t_plus_7"):
        spec = FEATURE_REGISTRY[f"gauge.target_{horizon}"]
        assert "target" in spec.leakage_rule.lower()


def test_build_gauge_features_against_real_gold_gauge_daily_if_present():
    path = REPO_ROOT / "data" / "analytics" / "gold" / "datasets" / "gold_gauge_daily.jsonl"
    if not path.exists():
        pytest.skip("data/analytics/gold/datasets/ not generated in this environment")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    df = build_gauge_features(records)
    assert set(GAUGE_FEATURE_COLUMNS).issubset(df.columns)
    assert len(df) == len(records)
    complete = df.dropna(subset=GAUGE_FEATURE_COLUMNS + ["target_t_plus_1"])
    assert len(complete) > 0  # real data genuinely produces usable feature rows
