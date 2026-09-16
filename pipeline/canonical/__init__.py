"""Canonical, source-independent records produced after source parsing."""

from .adapters import adapt_ndma, adapt_pdma_gauge, adapt_pdma_rainfall, adapt_pmd_alerts, adapt_pmd_daily, adapt_pmd_weekly
from .output import write_jsonl

__all__ = [
    "adapt_ndma", "adapt_pdma_gauge", "adapt_pdma_rainfall", "adapt_pmd_alerts", "adapt_pmd_daily", "adapt_pmd_weekly", "write_jsonl",
]
