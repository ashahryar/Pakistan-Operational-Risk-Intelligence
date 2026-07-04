"""
downloader.py

Reusable PDF downloader.
"""

import logging
from pathlib import Path

from .fetcher import HTTPClient


client = HTTPClient()


def download_file(
    url: str,
    output: Path,
) -> bool:
    """
    Download any file.
    """

    response = client.get(url)

    if response is None:
        return False

    try:

        with open(output, "wb") as f:
            f.write(response.content)

        logging.info("Downloaded %s", output.name)

        return True

    except OSError as e:

        logging.error(e)

        return False