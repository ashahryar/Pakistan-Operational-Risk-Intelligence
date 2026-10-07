"""dashboard/utils/api_cache.py

Task 41 -- the cache boundary for API reads.

`st.cache_data` pickles what a function returns. `ApiResult` is a dataclass defined in `dashboard.api_client`; pickle stores it by
reference to that module's class, so as soon as the module object is replaced (Streamlit's file watcher purges changed modules from a
long-running server) the instance no longer matches `dashboard.api_client.ApiResult` and Streamlit raises UnserializableReturnValueError.

The rule here: **only a plain dict crosses the cache.** `cached_api` caches `{ok, data, error_kind, message, status_code, fetched_at}`
and rebuilds the ApiResult on the way out. A failed call (ok=False) is raised inside the cached function, so Streamlit never stores it:
the next run retries, and the caller still receives the same error kind, message and status code (and body, for the 503-with-evidence case).
"""

from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Any, Callable

import streamlit as st

from dashboard.api_client import ApiResult

PAYLOAD_KEYS = ("ok", "data", "error_kind", "message", "status_code", "fetched_at")


class ApiCallFailed(Exception):
    """Raised inside a cached function so that Streamlit does not cache a failed API call."""

    def __init__(self, payload: dict):
        super().__init__(payload.get("message") or payload.get("error_kind") or "api call failed")
        self.payload = payload


def to_payload(result: ApiResult) -> dict:
    return {"ok": bool(result.ok), "data": result.data, "error_kind": result.error_kind, "message": result.message,
            "status_code": result.status_code, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def from_payload(payload: dict) -> ApiResult:
    return ApiResult(bool(payload["ok"]), data=payload.get("data"), error_kind=payload.get("error_kind"), message=payload.get("message"),
                     status_code=payload.get("status_code"))


def cached_api(ttl: int = 300) -> Callable[[Callable[..., ApiResult]], Callable[..., ApiResult]]:
    """Decorate a function returning ApiResult. Successful results are cached for `ttl` seconds as plain dicts; failures are never cached.

    The wrapper exposes `.clear()` (drop this function's entries), `.ttl`, and `.payload(*args)` (the cached plain dict, with `fetched_at`)."""

    def decorate(fn: Callable[..., ApiResult]) -> Callable[..., ApiResult]:
        key = f"{fn.__module__}.{fn.__qualname__}"

        @st.cache_data(ttl=ttl, show_spinner=False)
        def _cached(fn_key: str, *args: Any, **kwargs: Any) -> dict:         # fn_key is hashed into the cache key (Streamlit skips underscore-prefixed args): two functions never share an entry
            payload = to_payload(fn(*args, **kwargs))
            if not payload["ok"]:
                raise ApiCallFailed(payload)
            return payload

        def payload(*args: Any, **kwargs: Any) -> dict:
            try:
                return _cached(key, *args, **kwargs)
            except ApiCallFailed as e:
                return e.payload

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> ApiResult:
            return from_payload(payload(*args, **kwargs))

        wrapper.clear = _cached.clear          # type: ignore[attr-defined]
        wrapper.ttl = ttl                      # type: ignore[attr-defined]
        wrapper.payload = payload              # type: ignore[attr-defined]
        return wrapper

    return decorate


def render_refresh_control(where=None, label: str = "Refresh data") -> None:
    """A manual refresh: drops every cached read (API and database) and reruns the page, so new rows are picked up without a restart."""
    target = where if where is not None else st.sidebar
    if target.button(label, help="Reload from the API and database now. Data is also re-read automatically when its cache expires (1-5 minutes).",
                     key=f"refresh_{label}"):
        st.cache_data.clear()
        st.rerun()
