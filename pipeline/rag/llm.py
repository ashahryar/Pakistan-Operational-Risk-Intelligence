"""LLM provider abstraction for grounded answers. The retrieval layer knows nothing about any provider.

    provider.generate(system, question, evidence, constraints) -> LLMResult

Two small providers use only the standard library (no SDK, no agent framework): `anthropic` (Messages API) and
`openai_compatible` (chat-completions API; also used by many self-hosted servers). Configuration is by environment variable;
nothing is read from a file and no credential is ever logged or placed in an error message:

    PORI_LLM_PROVIDER   anthropic | openai_compatible        (unset = no provider configured)
    PORI_LLM_MODEL      model id (required, no default is assumed)
    PORI_LLM_API_KEY    credential
    PORI_LLM_BASE_URL   optional endpoint override
    PORI_LLM_TIMEOUT    seconds (default 30)
    PORI_LLM_MAX_TOKENS answer length cap (default 600)

The providers were exercised only against a mocked transport (no credential was available when they were written).
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Protocol, Sequence


class LLMError(Exception):
    """Base class: the provider could not produce a usable response."""
    kind = "error"


class LLMUnavailable(LLMError):
    kind = "not_configured"


class LLMTimeout(LLMError):
    kind = "timeout"


class LLMRequestError(LLMError):
    kind = "request_failed"


class LLMMalformedResponse(LLMError):
    kind = "malformed_response"


@dataclass(frozen=True)
class GenerationConstraints:
    max_tokens: int = 600
    temperature: float = 0.0
    timeout: float = 30.0


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str
    usage: Optional[dict] = None


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, question: str, evidence: Sequence[dict], constraints: GenerationConstraints) -> LLMResult: ...


def render_user_message(question: str, evidence: Sequence[dict]) -> str:
    """The evidence block + question sent to the model. Each item is addressed by its citation id."""
    parts = ["SUPPLIED INFORMATION (the only information you may use):" if any(e.get("kind") for e in evidence)
             else "EVIDENCE (the only information you may use):"]
    for e in evidence:
        if e.get("kind") == "risk_engine":                       # Task 32: computed context, a different provenance from the document chunks
            r = e["record"]
            lk = e.get("lookup") or {}
            sig = ", ".join(f"{k}={v}" for k, v in (r.get("signals") or {}).items())
            parts.append("\n".join([
                "--- [risk_engine] --- COMPUTED BY THE RISK ENGINE (provenance RISK_ENGINE; not a document, cite as [risk_engine])",
                f"area: {r.get('admin_unit_name')} (admin_unit_id {r.get('admin_unit_id')}, level {r.get('admin_level')}), province: {r.get('province')}",
                f"risk_date: {r.get('risk_date')} (lookup: {lk.get('basis')})",
                f"risk_status: {r.get('risk_status')}",
                f"risk_basis: {r.get('risk_basis')}",
                f"risk_confidence: {r.get('risk_confidence')}",
                f"risk_score: {r.get('risk_score')} (null = not computed)",
                f"signals (0-1): {sig}",
                f"top_risk_domain: {r.get('top_risk_domain')}",
                f"data_coverage_pct: {r.get('data_coverage_pct')}",
                f"active/observed/missing signals: {r.get('active_signal_count')}/{r.get('observed_signal_count')}/{r.get('missing_signal_count')}",
                f"calculation_version: {r.get('calculation_version')}",
                f"threshold_status: {r.get('threshold_status')}"]))
            continue
        g = e.get("geography") or {}
        ev = e.get("event") or {}
        parts.append(
            f"--- [chunk:{e['chunk_id']}] ---\n"
            f"document_id: {e.get('document_id')}\nsource: {e.get('source')} ({e.get('source_type')})\ntitle: {e.get('title')}\n"
            f"document_date: {e.get('document_date')}\n"
            f"geography: province={g.get('province')} district/unit={g.get('admin_unit_name')} status={g.get('status')}\n"
            f"event_type: {ev.get('event_type')}\nsource_reference: {e.get('url') or e.get('file_path')}\n"
            f"retrieval: {e.get('relevance_summary')}\ntext:\n{e.get('text')}")
    parts.append(f"\nQUESTION: {question}")
    return "\n".join(parts)


Transport = Callable[[str, Mapping[str, str], bytes, float], "tuple[int, bytes]"]


def urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> "tuple[int, bytes]":
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 (https endpoint chosen by the operator)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (socket.timeout, TimeoutError) as e:
        raise LLMTimeout("the LLM provider did not answer in time") from e
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            raise LLMTimeout("the LLM provider did not answer in time") from e
        raise LLMRequestError("the LLM provider could not be reached") from e


class _HttpProvider:
    name = "base"
    default_base_url = ""

    def __init__(self, model: str, api_key: str, base_url: Optional[str] = None, transport: Transport = urllib_transport):
        if not model or not api_key:
            raise LLMUnavailable("an LLM model and API key are required")
        self.model, self._key, self._transport = model, api_key, transport
        self.base_url = (base_url or self.default_base_url).rstrip("/")

    def _post(self, url: str, headers: dict, payload: dict, timeout: float) -> dict:
        status, raw = self._transport(url, headers, json.dumps(payload).encode("utf-8"), timeout)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise LLMMalformedResponse("the LLM provider returned a non-JSON response") from e
        if status != 200:                                            # never echo the request (it carries the credential)
            err = data.get("error") if isinstance(data, dict) else None
            msg = err.get("message") if isinstance(err, dict) else None
            raise LLMRequestError(f"the LLM provider answered HTTP {status}" + (f": {str(msg)[:160]}" if msg else ""))
        if not isinstance(data, dict):
            raise LLMMalformedResponse("unexpected response shape")
        return data


class AnthropicProvider(_HttpProvider):
    name = "anthropic"
    default_base_url = "https://api.anthropic.com"

    def generate(self, system, question, evidence, constraints):
        data = self._post(f"{self.base_url}/v1/messages",
                          {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          {"model": self.model, "max_tokens": constraints.max_tokens, "temperature": constraints.temperature, "system": system,
                           "messages": [{"role": "user", "content": render_user_message(question, evidence)}]}, constraints.timeout)
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise LLMMalformedResponse("missing 'content' in the response")
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        if not text.strip():
            raise LLMMalformedResponse("the response contained no text")
        return LLMResult(text, self.name, str(data.get("model") or self.model), data.get("usage") if isinstance(data.get("usage"), dict) else None)


class OpenAICompatibleProvider(_HttpProvider):
    name = "openai_compatible"
    default_base_url = "https://api.openai.com/v1"

    def generate(self, system, question, evidence, constraints):
        data = self._post(f"{self.base_url}/chat/completions",
                          {"Authorization": f"Bearer {self._key}", "content-type": "application/json"},
                          {"model": self.model, "max_tokens": constraints.max_tokens, "temperature": constraints.temperature,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": render_user_message(question, evidence)}]}, constraints.timeout)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMMalformedResponse("missing choices[0].message.content in the response") from e
        if not isinstance(text, str) or not text.strip():
            raise LLMMalformedResponse("the response contained no text")
        return LLMResult(text, self.name, str(data.get("model") or self.model), data.get("usage") if isinstance(data.get("usage"), dict) else None)


PROVIDERS = {"anthropic": AnthropicProvider, "openai_compatible": OpenAICompatibleProvider}


def constraints_from_env(env: Optional[Mapping[str, str]] = None) -> GenerationConstraints:
    env = os.environ if env is None else env
    try:
        return GenerationConstraints(max_tokens=int(env.get("PORI_LLM_MAX_TOKENS", 600)), timeout=float(env.get("PORI_LLM_TIMEOUT", 30)))
    except ValueError:
        return GenerationConstraints()


def provider_from_env(env: Optional[Mapping[str, str]] = None, transport: Transport = urllib_transport) -> LLMProvider:
    """Build the configured provider or raise LLMUnavailable (the API turns that into a 503)."""
    env = os.environ if env is None else env
    name = (env.get("PORI_LLM_PROVIDER") or "").strip().lower()
    if not name:
        raise LLMUnavailable("no LLM provider is configured (set PORI_LLM_PROVIDER, PORI_LLM_MODEL and PORI_LLM_API_KEY)")
    if name not in PROVIDERS:
        raise LLMUnavailable(f"unknown LLM provider '{name}' (supported: {', '.join(sorted(PROVIDERS))})")
    return PROVIDERS[name](env.get("PORI_LLM_MODEL", ""), env.get("PORI_LLM_API_KEY", ""), env.get("PORI_LLM_BASE_URL") or None, transport)
