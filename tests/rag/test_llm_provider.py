"""Task 31 -- LLM provider contract tests. NO network and NO credential: every request goes through a mocked transport.
The providers were never run against a live endpoint; an optional live test (tests/rag/test_llm_live.py) exists for that."""

import json

import pytest

from pipeline.rag.llm import (
    AnthropicProvider,
    GenerationConstraints,
    LLMMalformedResponse,
    LLMRequestError,
    LLMTimeout,
    LLMUnavailable,
    OpenAICompatibleProvider,
    constraints_from_env,
    provider_from_env,
    render_user_message,
)

KEY = "sk-test-SECRET-123"
EVIDENCE = [{"chunk_id": "ndma:sitrep:a#c0001", "document_id": "ndma:sitrep:a", "source": "ndma", "source_type": "sitrep", "title": "Sitrep 12",
             "document_date": "2026-07-05", "geography": {"province": "Punjab", "admin_unit_name": None, "status": "resolved"},
             "event": {"event_type": "flood"}, "url": None, "file_path": "data/parsed/a.json", "text": "45 deaths were reported.",
             "relevance_summary": "type=semantic_vector, score=0.71"}]
C = GenerationConstraints(max_tokens=100, temperature=0.0, timeout=5)


class Transport:
    def __init__(self, status=200, body=None, raw=None, exc=None):
        self.status, self.body, self.raw, self.exc, self.calls = status, body, raw, exc, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, dict(headers), json.loads(body), timeout))
        if self.exc:
            raise self.exc
        return self.status, self.raw if self.raw is not None else json.dumps(self.body).encode()


ANTH_OK = {"content": [{"type": "text", "text": "answer [chunk:ndma:sitrep:a#c0001]"}], "model": "m-1", "usage": {"input_tokens": 5}}
OAI_OK = {"choices": [{"message": {"content": "answer [chunk:ndma:sitrep:a#c0001]"}}], "model": "m-1", "usage": {"total_tokens": 7}}


def test_message_carries_every_evidence_field_and_the_citation_identifier():
    msg = render_user_message("How many died?", EVIDENCE)
    for needle in ("[chunk:ndma:sitrep:a#c0001]", "document_id: ndma:sitrep:a", "source: ndma (sitrep)", "title: Sitrep 12", "document_date: 2026-07-05",
                   "province=Punjab", "event_type: flood", "data/parsed/a.json", "type=semantic_vector", "45 deaths were reported.", "QUESTION: How many died?"):
        assert needle in msg


def test_anthropic_provider_request_and_response():
    t = Transport(body=ANTH_OK)
    r = AnthropicProvider("m-1", KEY, transport=t).generate("SYS", "q?", EVIDENCE, C)
    assert (r.text, r.provider, r.model, r.usage) == ("answer [chunk:ndma:sitrep:a#c0001]", "anthropic", "m-1", {"input_tokens": 5})
    url, headers, body, timeout = t.calls[0]
    assert url == "https://api.anthropic.com/v1/messages" and headers["x-api-key"] == KEY and timeout == 5
    assert body["system"] == "SYS" and body["max_tokens"] == 100 and body["temperature"] == 0 and "45 deaths" in body["messages"][0]["content"]


def test_openai_compatible_provider_request_and_response_with_base_url_override():
    t = Transport(body=OAI_OK)
    r = OpenAICompatibleProvider("m-1", KEY, "http://llm.local/v1/", t).generate("SYS", "q?", EVIDENCE, C)
    assert r.text.startswith("answer") and r.provider == "openai_compatible"
    url, headers, body, _ = t.calls[0]
    assert url == "http://llm.local/v1/chat/completions" and headers["Authorization"] == f"Bearer {KEY}"
    assert body["messages"][0] == {"role": "system", "content": "SYS"} and "45 deaths" in body["messages"][1]["content"]


@pytest.mark.parametrize("cls", [AnthropicProvider, OpenAICompatibleProvider])
def test_timeout_is_a_typed_error(cls):
    with pytest.raises(LLMTimeout):
        cls("m", KEY, transport=Transport(exc=LLMTimeout("slow"))).generate("S", "q", EVIDENCE, C)


@pytest.mark.parametrize("cls,raw", [(AnthropicProvider, b"<html>gateway</html>"), (OpenAICompatibleProvider, b"not json"),
                                     (AnthropicProvider, b"[]"), (OpenAICompatibleProvider, b"[]")])
def test_malformed_json_is_a_typed_error(cls, raw):
    with pytest.raises(LLMMalformedResponse):
        cls("m", KEY, transport=Transport(raw=raw)).generate("S", "q", EVIDENCE, C)


@pytest.mark.parametrize("cls,body", [(AnthropicProvider, {}), (AnthropicProvider, {"content": []}), (AnthropicProvider, {"content": [{"type": "text", "text": "  "}]}),
                                      (OpenAICompatibleProvider, {}), (OpenAICompatibleProvider, {"choices": []}),
                                      (OpenAICompatibleProvider, {"choices": [{"message": {"content": None}}]})])
def test_malformed_shape_is_a_typed_error(cls, body):
    with pytest.raises(LLMMalformedResponse):
        cls("m", KEY, transport=Transport(body=body)).generate("S", "q", EVIDENCE, C)


def test_http_error_is_typed_and_never_echoes_the_credential():
    t = Transport(status=401, body={"error": {"message": "invalid x-api-key"}})
    with pytest.raises(LLMRequestError) as e:
        AnthropicProvider("m", KEY, transport=t).generate("S", "q", EVIDENCE, C)
    assert "401" in str(e.value) and KEY not in str(e.value) and KEY not in repr(e.value)


def test_missing_model_or_key_is_unavailable():
    for model, key in (("", KEY), ("m", ""), ("", "")):
        with pytest.raises(LLMUnavailable):
            AnthropicProvider(model, key)


def test_env_configuration():
    with pytest.raises(LLMUnavailable, match="no LLM provider"):
        provider_from_env({})
    with pytest.raises(LLMUnavailable, match="unknown"):
        provider_from_env({"PORI_LLM_PROVIDER": "nope"})
    with pytest.raises(LLMUnavailable):
        provider_from_env({"PORI_LLM_PROVIDER": "anthropic", "PORI_LLM_MODEL": "m"})               # key missing
    p = provider_from_env({"PORI_LLM_PROVIDER": "OpenAI_Compatible", "PORI_LLM_MODEL": "m", "PORI_LLM_API_KEY": KEY, "PORI_LLM_BASE_URL": "http://x/v1"})
    assert isinstance(p, OpenAICompatibleProvider) and p.model == "m" and p.base_url == "http://x/v1"
    assert KEY not in repr(p.__dict__.get("base_url"))


def test_constraints_from_env_with_defaults_and_bad_values():
    assert constraints_from_env({}) == GenerationConstraints(600, 0.0, 30.0)
    assert constraints_from_env({"PORI_LLM_TIMEOUT": "7", "PORI_LLM_MAX_TOKENS": "50"}) == GenerationConstraints(50, 0.0, 7.0)
    assert constraints_from_env({"PORI_LLM_TIMEOUT": "abc"}) == GenerationConstraints()


def test_no_credential_or_provider_name_is_hard_coded_outside_the_provider_module():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    for rel in ("pipeline/rag/retrieval.py", "pipeline/rag/hybrid.py", "pipeline/rag/semantic.py", "pipeline/rag/grounding.py"):
        src = (root / rel).read_text(encoding="utf-8").lower()
        assert "anthropic" not in src and "openai" not in src and "api_key" not in src


# ------------------------------------------------------------------ the REAL urllib transport against a local mock HTTP server (no external network)
import threading  # noqa: E402
import time  # noqa: E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402


@pytest.fixture
def mock_server():
    state = {"mode": "ok", "seen": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["seen"].append((self.path, self.headers.get("Authorization"), body))
            if state["mode"] == "slow":
                time.sleep(1.5)
            code, payload = (500, {"error": {"message": "boom"}}) if state["mode"] == "error" else (200, OAI_OK)
            raw = b"garbage" if state["mode"] == "garbage" else json.dumps(payload).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_real_transport_success_and_request_shape(mock_server):
    state, base = mock_server
    r = OpenAICompatibleProvider("m-1", KEY, base).generate("SYS", "q?", EVIDENCE, GenerationConstraints(timeout=5))
    assert r.text.startswith("answer")
    path, auth, body = state["seen"][0]
    assert path == "/v1/chat/completions" and auth == f"Bearer {KEY}" and body["model"] == "m-1"


def test_real_transport_http_500_garbage_and_timeout_and_unreachable(mock_server):
    state, base = mock_server
    p = OpenAICompatibleProvider("m-1", KEY, base)
    state["mode"] = "error"
    with pytest.raises(LLMRequestError, match="HTTP 500"):
        p.generate("S", "q", EVIDENCE, GenerationConstraints(timeout=5))
    state["mode"] = "garbage"
    with pytest.raises(LLMMalformedResponse):
        p.generate("S", "q", EVIDENCE, GenerationConstraints(timeout=5))
    state["mode"] = "slow"
    with pytest.raises(LLMTimeout):
        p.generate("S", "q", EVIDENCE, GenerationConstraints(timeout=0.3))
    with pytest.raises((LLMRequestError, LLMTimeout)):                          # refused (Linux) or slow to refuse within the timeout (Windows)
        OpenAICompatibleProvider("m", KEY, "http://127.0.0.1:9/v1").generate("S", "q", EVIDENCE, GenerationConstraints(timeout=2))
