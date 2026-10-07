"""Task 41 -- the API cache boundary: no ApiResult ever crosses st.cache_data, failures are never cached, and the error semantics survive."""

import ast
import contextlib
import importlib
import pickle
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "dashboard"


@contextlib.contextmanager
def replaced_client_module():
    """Simulate a server replacing dashboard.api_client, then put the ORIGINAL class objects back so other tests keep patching the classes the pages use."""
    import dashboard.api_client as client
    originals = (client.ApiResult, client.RiskApiClient)
    try:
        importlib.reload(client)
        yield client
    finally:
        client.ApiResult, client.RiskApiClient = originals


def _fresh_cache_module():
    import dashboard.utils.api_cache as m
    return importlib.reload(m)


def test_root_cause_a_replaced_api_client_module_makes_an_apiresult_unpicklable():
    """Reproduces the Task 40 crash: Streamlit pickles cache return values, and pickle stores a dataclass by reference to its module's class.
    When the module object is replaced (a long-running server purges changed modules) the old instance no longer matches `dashboard.api_client.ApiResult`."""
    import dashboard.api_client as client
    old = client.ApiResult(True, data=[1])
    assert pickle.loads(pickle.dumps(old)) == old                       # fine while the module is unchanged
    with replaced_client_module():                                       # a new class object under the same name
        with pytest.raises(pickle.PicklingError, match="not the same object"):
            pickle.dumps(old)


def test_cached_api_survives_the_module_reload_that_broke_apiresult():
    import dashboard.api_client as client
    mod = _fresh_cache_module()
    calls = []

    @mod.cached_api(ttl=60)
    def read(base):
        calls.append(base)
        return client.ApiResult(True, data={"n": 1}, status_code=200)

    mod_clear = read.clear
    mod_clear()
    first = read("http://x")
    with replaced_client_module():                                       # the very event that made the raw ApiResult unserialisable
        second = read("http://x")                                        # served from cache: must not raise
    assert first.ok and second.ok and second.data == {"n": 1} and second.status_code == 200
    assert calls == ["http://x"]                                         # one real call: the second was a cache hit


def test_a_cached_payload_is_pickle_safe_plain_data():
    mod = _fresh_cache_module()
    import dashboard.api_client as client

    @mod.cached_api(ttl=60)
    def read(base):
        return client.ApiResult(True, data=[{"a": 1}], status_code=200)

    read.clear()
    payload = read.payload("b")
    assert type(payload) is dict and set(payload) == set(mod.PAYLOAD_KEYS)
    assert pickle.loads(pickle.dumps(payload)) == payload
    assert payload["fetched_at"].endswith("+00:00")


def test_failures_are_not_cached_and_keep_their_kind_message_status_and_body():
    mod = _fresh_cache_module()
    import dashboard.api_client as client
    calls = []
    outcomes = iter([client.ApiResult(False, data={"answer_status": "LLM_UNAVAILABLE"}, error_kind="unavailable", message="down", status_code=503),
                     client.ApiResult(False, error_kind="connection", message="no api"),
                     client.ApiResult(True, data=[1], status_code=200)])

    @mod.cached_api(ttl=60)
    def read(base):
        calls.append(1)
        return next(outcomes)

    read.clear()
    a = read("u")
    assert (a.ok, a.error_kind, a.message, a.status_code, a.data) == (False, "unavailable", "down", 503, {"answer_status": "LLM_UNAVAILABLE"})
    b = read("u")                                                        # the failure was not kept: this is a fresh call with a different outcome
    assert (b.ok, b.error_kind, b.status_code) == (False, "connection", None)
    c = read("u")
    assert c.ok and c.data == [1]
    read("u")                                                            # success IS cached
    assert len(calls) == 3


def test_functions_never_share_a_cache_entry_and_clear_forces_a_refresh():
    mod = _fresh_cache_module()
    import dashboard.api_client as client

    @mod.cached_api(ttl=60)
    def one(base):
        return client.ApiResult(True, data="one")

    @mod.cached_api(ttl=60)
    def two(base):
        return client.ApiResult(True, data="two")

    one.clear()
    two.clear()
    assert one("b").data == "one" and two("b").data == "two"
    state = {"v": "new"}

    @mod.cached_api(ttl=60)
    def changing(base):
        return client.ApiResult(True, data=state["v"])

    changing.clear()
    assert changing("b").data == "new"
    state["v"] = "newer"
    assert changing("b").data == "new"                                   # cached until the TTL ends or the user refreshes
    changing.clear()
    assert changing("b").data == "newer"                                 # a refresh picks up the new value without a restart
    assert changing.ttl == 60


def test_every_dashboard_cache_data_function_returns_serialisable_values():
    """Static guard over the whole dashboard: a function decorated with st.cache_data must not touch the API client at all."""
    offenders = []
    for path in DASHBOARD.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            decos = [ast.unparse(d) for d in fn.decorator_list]
            if not any("cache_data" in d for d in decos):
                continue
            body = ast.unparse(fn)
            if any(token in body for token in ("_client()", "RiskApiClient", "ApiResult", "api_client")):
                offenders.append(f"{path.relative_to(ROOT)}::{fn.name}")
    # api_cache.py's own inner cached function is the one allowed place: it converts to a plain dict before returning
    offenders = [o for o in offenders if not o.startswith("dashboard\\utils\\api_cache.py") and not o.startswith("dashboard/utils/api_cache.py")]
    assert offenders == [], f"st.cache_data functions that return API results: {offenders}"


def test_the_three_reported_functions_use_the_cache_boundary():
    for rel, names in {"Home.py": ["_risk_latest"], "pages/5_PDMA_Rivers.py": ["_evidence"], "pages/6_Risk_Map.py": ["_provinces"]}.items():
        tree = ast.parse((DASHBOARD / rel).read_text(encoding="utf-8"))
        funcs = {n.name: [ast.unparse(d) for d in n.decorator_list] for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for name in names:
            assert any(d.startswith("cached_api") for d in funcs[name]), f"{rel}::{name} must use @cached_api"
            assert not any("cache_data" in d for d in funcs[name])


@pytest.fixture(autouse=True)
def _restore_modules():
    yield
    sys.modules.pop("dashboard.utils.api_cache", None)
