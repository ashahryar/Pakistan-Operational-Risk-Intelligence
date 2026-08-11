"""
dashboard/utils/helpers.py

Shared helper functions used across more than one component/section.

Phase 2D adds `classify_river_risk`, consolidating a classification
rule that previously existed independently in three places inside
sections/hydrology.py (gauge status, flow-status fallback, and the
river-table Risk column) — same thresholds, same output labels, no
calculation change.
"""

import pandas as pd


def classify_river_risk(current_level, danger_level) -> str:
    """
    Classify a single river gauge reading against its danger level.

    Returns one of "Danger", "Watch", "Normal", or "Unknown" (when
    either value is missing). Thresholds are unchanged from the
    original hydrology logic:
      - current_level >= danger_level            -> "Danger"
      - current_level >= danger_level * 0.90      -> "Watch"
      - otherwise                                 -> "Normal"
    """

    if pd.isna(current_level) or pd.isna(danger_level):

        return "Unknown"

    if current_level >= danger_level:

        return "Danger"

    if current_level >= danger_level * 0.90:

        return "Watch"

    return "Normal"