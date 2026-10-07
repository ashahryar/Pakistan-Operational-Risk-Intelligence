# Operational intelligence agent — status (Task 34)

**What it is:** a read-only, provenance-aware operational intelligence agent that orchestrates existing trusted PORI capabilities. It is **not** an autonomous agent, not a new reasoning or data source, and not a framework: it is a fixed pipeline (guardrails → intent → geography → tool plan → allowlisted read-only tools → separate provenance-labelled blocks → optional grounded generation → audit trace) in the pure package `pipeline/agents/`.

**What it can never do:** write data, change a risk status, run SQL, read files, run commands, request an arbitrary URL, call itself, treat a document as a risk input, present a baseline forecast as validated ML, guess a geography, or produce a natural-language answer that a real language model did not write and the existing grounding validation did not accept.

## Pipeline

```text
request
  1 policy guardrails        deterministic refusals (UNSUPPORTED_REQUEST); the model never sees a refused request and can never lift a refusal
  2 analysis / intent        regex facets + the existing pure date/event helpers -> one of 8 intents
  3 geography (mandatory)    geography.resolve_place (existing exact/alias/normalised resolver, never fuzzy) or geography.get_admin_unit (explicit admin_unit_id)
                             ambiguous -> AMBIGUOUS_GEOGRAPHY + candidates; unrecognised place -> UNSUPPORTED_REQUEST; nothing is guessed
  4 plan                     deterministic plan; OR (provider available, routing=auto) a model-proposed plan validated against the typed contract
  5 execute                  ToolExecutor: validate -> run the injected read-only backend -> ToolResult{tool_name, arguments, status, result, provenance}
  6 assemble                 risk_context (RISK_ENGINE) | documentary_evidence (RAG_DOCUMENT) | ml_prediction (ML_MODEL / BASELINE_MODEL) | geography (GEOGRAPHY)
  7 generate (optional)      only with a real provider: the EXISTING answer_intelligence() + validate_intelligence_answer() (Task 31/32/33 rules). No second grounding implementation
  8 trace                    request, policy, analysis, routing, validated plan, tool statuses + provenance, generation outcome, final status, timestamps, plan fingerprint
```

Modules (`pipeline/agents/`): `contracts` (intents, statuses, provenance values, `ToolResult`), `policy` (guardrails), `tools` (closed allowlist + typed argument contracts), `executor`, `router` (deterministic intent + plan), `geography` (adapter over the existing resolver), `llm_router` (model-proposed plan validation), `assembly` (response blocks), `orchestrator` (control flow), `trace`. The API backends are in `api/app/services/agent.py` (thin adapters onto existing services); the endpoint is `api/app/routers/agent.py`.

## Intents

`CURRENT_RISK`, `HISTORICAL_RISK`, `DOCUMENT_SEARCH`, `EVIDENCE_GROUNDED_QUESTION` (a "why is X classified Y" question: delegated once to the existing intelligence service), `ML_FORECAST`, `GEOGRAPHY_LOOKUP`, `COMBINED_INTELLIGENCE`, `UNSUPPORTED`.

## Tools (closed allowlist, all read-only; `GET /api/v1/agent/tools` serves the contracts)

| Tool | Existing capability | Provenance |
|---|---|---|
| `geography.resolve_place` | `pipeline/intelligence/context.py` resolver over `scripts/geo/canonical_data.py` | GEOGRAPHY |
| `geography.get_admin_unit` | `geo.admin_unit` + `geo.current_boundary` (boundary availability) | GEOGRAPHY |
| `geography.list_units` | `list_admin_unit_summaries` | GEOGRAPHY |
| `risk.latest` / `risk.on_date` / `risk.history` / `risk.coverage` | risk serving views (`risk.latest_operational_risk`, `risk.operational_risk`) — Task 23 engine output unchanged | RISK_ENGINE |
| `rag.retrieve` (mode lexical / semantic / hybrid) | `retrieve_evidence` (Task 30/31 retrievers, unchanged) | RAG_DOCUMENT |
| `ml.predictions` / `ml.models` | `ml.predictions` / `ml.model_runs` (Task 33) | ML_MODEL for a validated model, BASELINE_MODEL for a baseline; none for INSUFFICIENT_DATA |
| `intelligence.ask` | the Task 32 service (never calls the agent: a test checks there is no `agent → intelligence → agent` import) | composite; each component keeps its own provenance |

There is no SQL, file-system, shell or HTTP tool, and no argument that can carry one: an unknown tool name is rejected before anything runs, arguments are typed and bounded, and free-text arguments are scanned for SQL, URLs and system access.

## Deterministic routing

Same input → same plan (the trace carries a `plan_fingerprint`; `replay_plan(trace, executor)` re-executes exactly the recorded validated calls). Facets: risk / forecast / documents / why / coverage / geography lookup. `risk+why` → `EVIDENCE_GROUNDED_QUESTION`; two or more of risk / forecast / documents → `COMBINED_INTELLIGENCE`; risk with a date or month → `HISTORICAL_RISK`. Documents are included in a combined plan when asked for explicitly or when the question is a "why" question; in that case they are optional (their absence does not block the answer). The deterministic router works with no model and is the fallback when a provider fails during routing. A question matching no capability, or a place the canonical geography does not know, is refused rather than guessed.

## LLM-assisted routing

With a real provider and `routing=auto`, the model may only *propose* `{"intent", "tool_calls"}` JSON. Every call is validated against the typed contract; `admin_unit_id` must be the area the deterministic geography step resolved (or the caller passed) and dates must be ones stated in the question or by the caller, so the model cannot invent an area or a date. Any invalid call rejects the whole plan: status `INVALID_TOOL_CALL`, **nothing is executed**, the rejected calls are visible in `tool_trace`. A model may decline (`MODEL_DECLINED`) but cannot widen scope or lift a policy refusal; routing never sees refused or unsupported requests. The model's raw text is not stored (only the parsed plan, or a short redacted excerpt when it cannot be parsed). Without a provider routing is deterministic. **Not measured:** how well a real model routes (no credential was available).

## Guardrails

Refused with `UNSUPPORTED_REQUEST` + a machine-readable `reason_code`: `ARBITRARY_SQL`, `MODIFY_DATA`, `CHANGE_RISK_STATUS`, `FABRICATE`, `DOCUMENTS_AS_RISK_INPUT`, `BASELINE_AS_VALIDATED_ML`, `EXTERNAL_WEB_REQUEST`, `SYSTEM_ACCESS`, `GEOGRAPHY_INFERENCE` (river / gauge / barrage → district), `GEOGRAPHY_LEVEL_UNSUPPORTED` (tehsil, town, union council …), plus `NO_SUPPORTED_INTENT`, `GEOGRAPHY_REQUIRED`, `GEOGRAPHY_NOT_RESOLVED`. These are wording heuristics: the real boundary is structural (closed allowlist, read-only backends, no such tool exists). A false premise ("why is Lahore HIGH?") is not refused: the engine value is returned with a `premise_check` that states the mismatch.

**Strengthened shared validator (found by a Task 34 test):** the Task 33 grounding validator did not reject an `[ml_prediction]` sentence calling a baseline forecast a "validated machine learning model". `pipeline/intelligence/grounding.py` now rejects it (`baseline_described_as_validated_ml`; a negated sentence such as "not a validated ML model" passes, and a genuinely validated model may be called validated). This also protects `/api/v1/intelligence/ask`.

## Provenance

Every tool result carries `provenance.sources ⊆ {RISK_ENGINE, RAG_DOCUMENT, ML_MODEL, BASELINE_MODEL, GEOGRAPHY}` (empty for a rejected call or an INSUFFICIENT_DATA forecast). The response keeps the blocks separate and adds `provenance` (per block + per tool) and `citations` (documentary / risk_engine / ml_prediction with the model attribution). Forecast rows are attributed by their status (`BASELINE_ONLY` → `BASELINE_MODEL` + the label "BASELINE_ONLY — NOT VALIDATED ML"; `PREDICTED` → `ML_MODEL`); `PREDICTED`, `BASELINE_ONLY` and `INSUFFICIENT_DATA` are never merged. The ML prediction layer still stores `ML_MODEL` on its rows (Task 33); the agent derives the finer attribution.

## API

`GET /api/v1/agent/ask?q=&admin_unit_id=&date=&mode=&routing=&top_k=` and `GET /api/v1/agent/tools`. Read-only: POST / PUT / PATCH / DELETE → 405; unknown parameters (`tool`, `sql`, `url`) are ignored; `q` 2–300 chars, `admin_unit_id` ≥ 1 (404 if unknown), `mode` lexical|semantic|hybrid, `routing` auto|deterministic (422 otherwise). Response fields: `question, status, status_reason, reason_code, intent, answer, geography, risk_context, risk_history, documentary_evidence, retrieval, ml_prediction, components, premise_check, tool_trace, citations, model, groundedness, provenance, policy, trace, disclaimer`. HTTP 503 only for `LLM_UNAVAILABLE` (the full structured body is still returned, as for `/rag/ask` and `/intelligence/ask`); every other status is 200. Statuses: `ANSWERED`, `COMPLETED`, `LLM_UNAVAILABLE`, `UNSUPPORTED_REQUEST`, `AMBIGUOUS_GEOGRAPHY`, `INSUFFICIENT_DATA`, `INVALID_TOOL_CALL`, `NO_EVIDENCE`, `INSUFFICIENT_EVIDENCE`, `INVALID_ANSWER`.

## Dashboard

`dashboard/pages/9_Agent.py`: question box, detected intent, status, routing, the answer only when `ANSWERED`, geography candidates, risk context, ML forecast (with the "BASELINE_ONLY — NOT VALIDATED ML" warning), documentary evidence, a provenance table, the tool trace and the full audit trace. No chat history is stored.

## Evaluation (frozen set `config/agent_eval.yaml`, harness `scripts/agents/evaluate_agent.py`, report `data/analytics/agent/agent_eval_report.json`)

36 hand-written cases on the real local data, no language model, lexical retrieval; small and one author, so it supports development decisions, not claims of accuracy.

| Measure | Result |
|---|---|
| Routing accuracy (intent) | 36/36 |
| Tool-selection accuracy (ordered tool list) | 36/36 |
| Status accuracy | 36/36 (35/36 before Task 35: D4 returned 5 off-topic chunks; see [`RAG_RELEVANCE_STATUS.md`](RAG_RELEVANCE_STATUS.md)) |
| Invalid-call rejection | 20/20 direct calls rejected with 0 backend invocations; 10/10 model-proposed plans rejected by the validator and 10/10 end to end (`INVALID_TOOL_CALL`, nothing but the geography step executed) |
| Provenance correctness | 192/192 checks (193 before Task 35: D4 no longer returns documents); 11/11 risk records equal an independent SQL read; 3/3 baseline forecasts labelled and attributed to BASELINE_MODEL; ML row statuses equal an independent SQL read |
| Abstention correctness | 21/21 abstained without facts (20/21 before Task 35); 0/36 cases with an answer |
| Grounding validation (scripted probes, not a model) | 9/9: the separated answer is ANSWERED; wrong status, false causality, baseline called validated ML, forecast as current risk / given a risk status, unknown citation, mixed provenance are withheld; abstention is reported |
| False-premise handling | 4/4 (3 wrong premises corrected from the engine value, 1 correct-premise control) |
| Reproducibility (same plan fingerprint on rerun) | 36/36 |

**D4 (fixed in Task 35):** "What did NDMA report about volcanic eruptions in Sindh?" originally returned 5 chunks instead of `NO_EVIDENCE` because lexical BM25 has no relevance floor. The relevance policy (`pipeline/rag/relevance.py`, no rule about volcanoes) now classifies those chunks `LOW_RELEVANCE`, and the agent reports `NO_EVIDENCE`. D4 belongs to the policy's selection pool, so the independent evidence is the fresh holdout described in `RAG_RELEVANCE_STATUS.md`.

## Limitations

* No real language model was available: LLM routing quality, answer quality and hallucination / causal-claim behaviour of a real model are **not measured**; the scripted-provider tests check our validators and the agent's handling only.
* The guardrails and the grounding checks are wording heuristics, not proofs; a paraphrased unsafe request or claim can slip past them (the structural limits — no SQL / file / shell / HTTP tool, read-only backends — do not depend on wording).
* Two-letter aliases (KP, GB) are not recognised in free text by the existing resolver (kept: no new matching); places are only recognised if they are canonical names or aliases.
* The relevance gate is a keyword-absence heuristic calibrated on a small set (see `RAG_RELEVANCE_STATUS.md` for its false-abstention cost and residual false positives); hybrid / semantic retrieval needs the embedding runtime (a lexical-only image answers those modes with a tool status `UNAVAILABLE`).
* The only ML target is the Lahore AQI baseline forecast (Task 33): every other area is `INSUFFICIENT_DATA`, and forecasts for other targets or horizons are never substituted.
* "Current" means the area's latest available risk record (its own maximum date), not today's date; the response states the risk date.
* No conversation memory, no write capability, no autonomous multi-step loop — by design.
