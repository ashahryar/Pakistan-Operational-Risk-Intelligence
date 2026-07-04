"""
fetcher.py

Reusable HTTP client for all extraction scripts.
"""

from .logger import setup_logger

logger = setup_logger("fetcher")
import time

import requests

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/137.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 2


class HTTPClient:
    """
    Reusable requests session.
    """

    def __init__(self):

        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def get(self, url: str):

        for attempt in range(1, MAX_RETRIES + 1):

            try:

                response = self.session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                )

                if response.status_code == 200:
                    return response

                logger.warning(
                    "Status %s for %s",
                    response.status_code,
                    url,
                )

            except requests.RequestException as e:

                logger.warning(
                    "Attempt %s failed : %s",
                    attempt,
                    e,
                )

            time.sleep(RETRY_DELAY)

        return None