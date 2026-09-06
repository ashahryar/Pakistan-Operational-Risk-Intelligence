"""
config/data_quality.py

Phase 1 / Task 5 (ADR-0001) — single shared place to tune data-quality
gate thresholds. See CLAUDE.md rule 5: "Fail the task when the rejection
ratio exceeds its threshold."

REJECTION_THRESHOLD is deliberately not lenient: 15% is low enough that
the historical PDMA rainfall defect (61 of 88 reports lost = 69%
rejection, reported as a green task) and any material NDMA/PMD
regression both correctly fail the task, while today's already-fixed
NDMA pipeline (~5.7% rejection, confirmed Phase 1 Task 3/4) stays green.
"""

REJECTION_THRESHOLD = 0.15
