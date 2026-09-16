"""
scripts/acquisition/client.py

Phase 1 / Task 15 (ADR-0001) -- a validating HTTP fetch layer for raw
acquisition. Reuses scripts/extraction/common/fetcher.py's HTTPClient
for its configured `requests.Session` (User-Agent, base setup) instead
of re-implementing session/header configuration -- but performs its
own single-attempt-with-explicit-retries request so the *actual* HTTP
status of every attempt is captured (the existing HTTPClient.get()
collapses every failure mode, including a definite 404, into a bare
`None`, which is fine for the existing scrapers but not precise enough
for acquisition provenance, which must record the real http_status).

Every fetch returns a FetchResult -- never raises, never silently
treats a failure as a success. Nothing here parses/transforms content
beyond the minimum needed to validate it (e.g. `json.loads` to confirm
a JSON response really is JSON) -- the raw bytes, not a parsed object,
are what gets handed to raw_store.save_raw_artifact().
"""

from __future__ import annotations

import json as _json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

from scripts.extraction.common.fetcher import DEFAULT_HEADERS

REQUEST_TIMEOUT = 60
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2

_session = requests.Session()
_session.headers.update(DEFAULT_HEADERS)


@dataclass
class FetchResult:
    url: str
    ok: bool
    http_status: Optional[int]
    content_type: Optional[str]
    content: Optional[bytes]
    byte_size: int
    retrieved_at: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    parsed_json: Optional[object] = field(default=None, repr=False)


def _raw_get(
    url: str, extra_headers: Optional[dict] = None
) -> tuple[Optional[requests.Response], Optional[str], Optional[str]]:
    """
    Single logical fetch with up to MAX_ATTEMPTS attempts, retrying
    only on connection/timeout errors (not on a real HTTP status code,
    which is meaningful information to preserve, not retry away).
    Returns (response_or_None, error_code_or_None, error_message_or_None).

    `extra_headers`, when given, are sent in addition to the session's
    default headers -- e.g. an Origin/Referer pair matching a source's
    own domain, exactly what that source's own front-end already sends
    when a browser loads its page. This is not a credential or an
    authorization bypass; it is the standard header set a normal
    browser visit already includes.
    """

    last_error_code = None
    last_error_message = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _session.get(url, timeout=REQUEST_TIMEOUT, headers=extra_headers), None, None
        except requests.Timeout as e:
            last_error_code, last_error_message = "timeout", str(e)
        except requests.ConnectionError as e:
            last_error_code, last_error_message = "connection_error", str(e)
        except requests.RequestException as e:
            last_error_code, last_error_message = "request_exception", str(e)

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    return None, last_error_code, last_error_message


def fetch(url: str, extra_headers: Optional[dict] = None) -> FetchResult:
    """
    Plain fetch with no content-type expectation -- captures whatever
    the server actually returned. Non-2xx status is recorded as a
    failure (`error_code='http_error'`), not silently accepted.
    """

    retrieved_at = datetime.now(timezone.utc)
    response, error_code, error_message = _raw_get(url, extra_headers=extra_headers)

    if response is None:
        return FetchResult(
            url=url, ok=False, http_status=None, content_type=None, content=None,
            byte_size=0, retrieved_at=retrieved_at, error_code=error_code, error_message=error_message,
        )

    content_type = response.headers.get("Content-Type")

    if not (200 <= response.status_code < 300):
        return FetchResult(
            url=url, ok=False, http_status=response.status_code, content_type=content_type,
            content=None, byte_size=0, retrieved_at=retrieved_at,
            error_code="http_error", error_message=f"HTTP {response.status_code}",
        )

    content = response.content

    if not content:
        return FetchResult(
            url=url, ok=False, http_status=response.status_code, content_type=content_type,
            content=None, byte_size=0, retrieved_at=retrieved_at,
            error_code="empty_response", error_message="server returned 0 bytes",
        )

    return FetchResult(
        url=url, ok=True, http_status=response.status_code, content_type=content_type,
        content=content, byte_size=len(content), retrieved_at=retrieved_at,
    )


def fetch_json(url: str, extra_headers: Optional[dict] = None) -> FetchResult:
    """
    Fetches `url` and validates that the response is genuinely parseable
    JSON. A non-JSON body (most commonly an HTML error page served with
    a 200 status, e.g. a maintenance page or a redirect-to-login page)
    is rejected with error_code='invalid_json' or 'unexpected_html' --
    it is never saved as if it were valid JSON data.
    """

    result = fetch(url, extra_headers=extra_headers)
    if not result.ok:
        return result

    stripped = result.content.lstrip()[:200].lower()
    if stripped.startswith(b"<!doctype html") or stripped.startswith(b"<html"):
        return FetchResult(
            url=url, ok=False, http_status=result.http_status, content_type=result.content_type,
            content=result.content, byte_size=result.byte_size, retrieved_at=result.retrieved_at,
            error_code="unexpected_html", error_message="response body looks like an HTML page, not JSON",
        )

    try:
        parsed = _json.loads(result.content)
    except (ValueError, UnicodeDecodeError) as e:
        return FetchResult(
            url=url, ok=False, http_status=result.http_status, content_type=result.content_type,
            content=result.content, byte_size=result.byte_size, retrieved_at=result.retrieved_at,
            error_code="invalid_json", error_message=str(e),
        )

    result.parsed_json = parsed
    return result


def fetch_binary(url: str, expected_content_type_prefixes: tuple[str, ...] = ()) -> FetchResult:
    """
    Fetches `url` for a binary artifact (e.g. a PDF). If
    `expected_content_type_prefixes` is given and the server's
    Content-Type header doesn't start with any of them, the fetch is
    rejected with error_code='content_type_mismatch' -- this is what
    catches a PDF link that actually 404s into an HTML error page
    served with status 200 (a real failure mode of WordPress/CMS sites
    like several sources in this inventory).
    """

    result = fetch(url)
    if not result.ok:
        return result

    if expected_content_type_prefixes and result.content_type:
        header = result.content_type.lower()
        if not any(header.startswith(p) for p in expected_content_type_prefixes):
            return FetchResult(
                url=url, ok=False, http_status=result.http_status, content_type=result.content_type,
                content=result.content, byte_size=result.byte_size, retrieved_at=result.retrieved_at,
                error_code="content_type_mismatch",
                error_message=f"expected one of {expected_content_type_prefixes}, got {result.content_type!r}",
            )

    return result
