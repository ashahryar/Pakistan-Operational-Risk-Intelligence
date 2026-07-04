"""
text_cleaner.py

Reusable text cleaning utilities.

Responsibilities:
- Normalize whitespace
- Remove duplicate blank lines
- Remove tabs
- Normalize unicode characters
"""

import re
import unicodedata


def normalize_unicode(text: str) -> str:
    """
    Normalize unicode characters.
    """

    return unicodedata.normalize("NFKC", text)


def remove_tabs(text: str) -> str:
    """
    Replace tabs with spaces.
    """

    return text.replace("\t", " ")


def remove_extra_spaces(text: str) -> str:
    """
    Collapse multiple spaces into one.
    """

    return re.sub(r"[ ]{2,}", " ", text)


def remove_empty_lines(text: str) -> str:
    """
    Remove duplicate blank lines.
    """

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def clean_text(text: str) -> str:
    """
    Complete cleaning pipeline.
    """

    text = normalize_unicode(text)
    text = remove_tabs(text)
    text = remove_extra_spaces(text)
    text = remove_empty_lines(text)

    return text.strip()