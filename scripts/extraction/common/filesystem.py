"""
filesystem.py

Handles all filesystem operations.

Responsibilities:
- Create folders
- Build raw data paths
- Build PDF paths
"""

from pathlib import Path


RAW_DATA = Path("data/raw")


def ensure_directory(path: Path) -> Path:
    """
    Create directory if it doesn't exist.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_report_directory(
    source: str,
    report_type: str,
    year: int,
) -> Path:
    """
    Example

    data/raw/pdma/reports/daily/2026
    """

    folder = (
        RAW_DATA
        / source
        / "reports"
        / report_type
        / str(year)
    )

    ensure_directory(folder)

    return folder


def get_pdf_directory(
    source: str,
    report_type: str,
    year: int,
) -> Path:
    """
    Example

    data/raw/pdma/reports/daily/2026/pdfs
    """

    pdf_folder = (
        get_report_directory(
            source,
            report_type,
            year,
        )
        / "pdfs"
    )

    ensure_directory(pdf_folder)

    return pdf_folder