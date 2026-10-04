"""Task 27 -- dashboard API client: every outcome is a result object, never an exception."""

import requests

from dashboard.api_client import ApiResult, RiskApiClient


class FakeResponse:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code, self._body, self._bad = status, body, bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._body


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.calls = response, exc, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if self.exc:
            raise self.exc
        return self.response


def client(resp=None, exc=None):
    s = FakeSession(resp, exc)
    return RiskApiClient(base_url="http://api.test/", timeout=3, session=s), s


def test_success_returns_data_and_builds_the_url_without_none_params():
    c, s = client(FakeResponse(200, [{"id": 1}]))
    r = c.admin_units(level=1, province=None)
    assert r.ok and r.data == [{"id": 1}] and not r.empty and r.status_code == 200
    url, params, timeout = s.calls[0]
    assert url == "http://api.test/api/v1/geography/admin-units" and params == {"level": 1, "limit": 500} and timeout == 3


def test_empty_result_is_ok_and_empty():
    r = client(FakeResponse(200, []))[0].risk(date="1999-01-01")
    assert r.ok and r.empty and r.data == []


def test_404_422_503_are_classified_with_friendly_messages():
    r404 = client(FakeResponse(404, {"detail": "admin_unit_id 5 not found in geo.admin_unit"}))[0].risk_latest(admin_unit_id=5)
    assert not r404.ok and r404.error_kind == "not_found" and r404.status_code == 404 and "not found" in r404.message
    r422 = client(FakeResponse(422, {"detail": [{"msg": "bad"}]}))[0].risk(date="x")
    assert r422.error_kind == "invalid_request" and "filter" in r422.message
    r503 = client(FakeResponse(503, {"detail": "Database query failed -- see server logs for details."}))[0].risk_map()
    assert r503.error_kind == "unavailable" and r503.status_code == 503 and "Traceback" not in r503.message


def test_other_status_codes_are_server_errors():
    r = client(FakeResponse(500, {"detail": "boom"}))[0].boundaries()
    assert not r.ok and r.error_kind == "server_error"


def test_timeout_and_connection_failures_do_not_raise():
    t = client(exc=requests.Timeout("slow"))[0].risk_latest()
    assert not t.ok and t.error_kind == "timeout"
    c = client(exc=requests.ConnectionError("refused"))[0].risk_latest()
    assert not c.ok and c.error_kind == "connection" and "not reachable" in c.message
    o = client(exc=requests.RequestException("odd"))[0].risk_latest()
    assert not o.ok and o.error_kind == "connection"


def test_unreadable_json_is_a_bad_response():
    r = client(FakeResponse(200, bad_json=True))[0].risk_map()
    assert not r.ok and r.error_kind == "bad_response"


def test_all_required_endpoints_are_called_with_their_filters():
    c, s = client(FakeResponse(200, {}))
    c.admin_units(level=2, province="Punjab"); c.boundaries(level=2, source="x"); c.risk_latest(risk_status="HIGH")  # noqa: E702
    c.risk(date="2026-09-16", province="Punjab", admin_unit_id=2, risk_status="LOW", limit=5, offset=10)
    c.risk_map(level=2, province="Sindh", risk_status="CRITICAL", only_with_risk=True, include_geometry=False)
    urls = [u.replace("http://api.test", "") for u, _, _ in s.calls]
    assert urls == ["/api/v1/geography/admin-units", "/api/v1/geography/boundaries", "/api/v1/risk/latest", "/api/v1/risk", "/api/v1/risk/map"]
    assert s.calls[3][1] == {"date": "2026-09-16", "province": "Punjab", "admin_unit_id": 2, "risk_status": "LOW", "limit": 5, "offset": 10}
    assert s.calls[4][1] == {"level": 2, "province": "Sindh", "risk_status": "CRITICAL", "only_with_risk": "true", "include_geometry": "false"}


def test_base_url_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PORI_API_URL", "http://example:9000/")
    assert RiskApiClient().base_url == "http://example:9000"
    monkeypatch.delenv("PORI_API_URL")
    assert RiskApiClient().base_url == "http://localhost:8000"


def test_api_result_is_immutable():
    r = ApiResult(True, data=[])
    try:
        r.ok = False  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
