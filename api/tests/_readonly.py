"""Shared read-only checks for the API tests.

`app.routes` cannot be used: in this FastAPI version included routers are wrapped (`_IncludedRouter`), so iterating
`app.routes` yields no APIRoute objects and any assertion over it passes vacuously. The generated OpenAPI document and real
HTTP requests reflect what the application actually exposes.
"""

from __future__ import annotations

import re

WRITE_VERBS = ("post", "put", "patch", "delete")


def openapi_methods(app, prefixes: tuple[str, ...]) -> dict[str, set[str]]:
    """{path: {lower-case methods}} for every OpenAPI path starting with one of `prefixes` (HTTP methods only)."""
    http = set(WRITE_VERBS) | {"get", "head", "options", "trace"}
    return {p: {m for m in ops if m in http} for p, ops in app.openapi()["paths"].items() if p.startswith(prefixes)}


def write_methods_exposed(app, prefixes: tuple[str, ...]) -> dict[str, set[str]]:
    return {p: m & set(WRITE_VERBS) for p, m in openapi_methods(app, prefixes).items() if m & set(WRITE_VERBS)}


def sample_url(path: str) -> str:
    """Fill OpenAPI path parameters with a harmless placeholder so a real request can be sent."""
    return re.sub(r"\{[^}]+\}", "sample", path)


def assert_read_only(app, client, prefixes: tuple[str, ...], expected_paths: set[str]) -> None:
    """Non-vacuous: the exact set of expected paths must exist, expose only GET, and answer every write verb with HTTP 405."""
    methods = openapi_methods(app, prefixes)
    assert set(methods) == expected_paths, f"unexpected API surface: {sorted(set(methods) ^ expected_paths)}"
    assert all(m == {"get"} for m in methods.values()), {p: m for p, m in methods.items() if m != {"get"}}
    assert write_methods_exposed(app, prefixes) == {}
    for path in sorted(methods):
        url = sample_url(path)
        for verb in WRITE_VERBS:
            r = getattr(client, verb)(url)
            assert r.status_code == 405, f"{verb.upper()} {url} -> {r.status_code}"
            assert "GET" in r.headers.get("allow", "")
