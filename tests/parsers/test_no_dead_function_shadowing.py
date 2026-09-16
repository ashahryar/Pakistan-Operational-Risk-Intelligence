"""
tests/parsers/test_no_dead_function_shadowing.py

Task 16A (Phase 1 / ADR-0001), Part A item 5 -- regression guard
against re-introducing the duplicate-definition shadowing bug the
Task 16 audit found in validation/rules.py and validation/translator.py
(each file defined a function twice; Python silently kept only the
second definition, leaving the first dead and confusing to future
editors). Static AST check: no top-level function name may be defined
more than once in either file.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _top_level_function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]


def test_validation_rules_has_no_duplicate_top_level_function_names():
    names = _top_level_function_names(PROJECT_ROOT / "validation" / "rules.py")
    dupes = [name for name, count in Counter(names).items() if count > 1]
    assert not dupes, f"validation/rules.py re-defines: {dupes}"


def test_validation_translator_has_no_duplicate_top_level_function_names():
    names = _top_level_function_names(PROJECT_ROOT / "validation" / "translator.py")
    dupes = [name for name, count in Counter(names).items() if count > 1]
    assert not dupes, f"validation/translator.py re-defines: {dupes}"


def test_validation_rules_still_exports_all_four_live_validators():
    names = set(_top_level_function_names(PROJECT_ROOT / "validation" / "rules.py"))
    assert {"valid_city", "valid_temperature", "valid_humidity", "valid_forecast"} <= names


def test_validation_translator_still_exports_normalize_city_and_lookups():
    names = set(_top_level_function_names(PROJECT_ROOT / "validation" / "translator.py"))
    assert {"normalize_city", "province_from_city", "district_from_city"} <= names
