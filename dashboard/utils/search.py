"""
dashboard/utils/search.py

Shared search helpers (Phase 2E, Module 2) used to provide a
consistent "search within table" experience across the Disaster,
Weather, and Hydrology sections instead of each section re-implementing
its own case-insensitive multi-column contains() filter.

No SQL/query logic — this only filters rows of dataframes that are
already loaded in memory.
"""

import pandas as pd
import streamlit as st


def render_search_box(label: str, key: str, placeholder: str = "") -> str:
    """
    Renders a standardized search text_input and returns the current
    (stripped) search term. Reusing this everywhere keeps label
    styling, placeholder tone, and icon usage consistent.
    """

    term = st.text_input(

        f"🔍 {label}",

        placeholder=placeholder,

        key=key,

    )

    return term.strip() if term else ""


def filter_dataframe_by_search(
    df: pd.DataFrame,
    search_term: str,
    columns: list,
) -> pd.DataFrame:
    """
    Case-insensitive substring search across one or more columns.

    - Returns `df` unchanged if `search_term` is blank or `df` is empty.
    - Only searches columns that actually exist in `df` (silently
      skips missing ones), so this is safe to call with a column list
      that doesn't perfectly match every dataset (e.g. searching
      ["station", "river"] on rainfall, which has no "river" column).
    - A row matches if the term is found in ANY of the given columns.
    """

    if not search_term or df.empty:
        return df

    term = search_term.lower()

    available_columns = [c for c in columns if c in df.columns]

    if not available_columns:
        return df

    mask = pd.Series(False, index=df.index)

    for col in available_columns:

        mask = mask | (

            df[col]

            .astype(str)

            .str.lower()

            .str.contains(term, na=False)

        )

    return df[mask]