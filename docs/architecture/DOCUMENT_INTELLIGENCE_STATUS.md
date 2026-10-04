# Document intelligence & RAG — status (Tasks 29, 30 and 31)

**Task 29 (implemented):** a traceable document/chunk store with provenance, a deterministic keyword (BM25) retriever and a read-only evidence API.
**Task 30 (implemented):** real text embeddings of every chunk, vector storage in PostgreSQL, and an optional semantic retrieval mode.
**Task 31 (implemented, NOT exercised against a real language model):** hybrid retrieval (BM25 + semantic, rank fusion) and a grounded-answer endpoint `GET /api/v1/rag/ask` that gives only retrieved chunks to an LLM, requires `[chunk:<id>]` citations, validates them deterministically and abstains rather than guessing. **No LLM credential exists in this environment**, so no real model has produced an answer in any test or evaluation here: the provider layer is covered by mocked-transport and scripted-provider tests, and the real endpoint answers 503 `LLM_UNAVAILABLE` (with the evidence) until `PORI_LLM_*` is configured.
**Not implemented:** autonomous agents, risk calculation inside RAG, re-ranking, query expansion, any claim of production-grade hallucination prevention. This is an evidence-grounded question-answering *pipeline*, not an authoritative assistant.

## Sources (existing parsed artifacts only; nothing scraped or copied)

| Reader | Input | Documents | Notes |
|---|---|---:|---|
| NDMA sitreps | `data/parsed/ndma/sitreps/*.json` (`raw_text`) | 96 | date, subject, parser-extracted province list and weather-event keywords |
| PDMA Punjab daily reports | `data/parsed/pdma/daily/*/*.json` (`forecast` + `weather_alert` text) | 138 | text is the forecast/alert boxes only; PDF extraction may interleave columns |
| FFC DFSR / GLOF alert | `data/parsed/canonical/document/tier1_ffc.jsonl` | 7 | has source URL, hazard topic |
| PMD-NDMC drought bulletins | `…/tier1_pmd_ndmc.jsonl` | 4 | no stated location; one has a reporting period |
| PMD weather alert | `data/parsed/pmd/weather_alerts/latest.json` | 1 | no issue date (only a scrape time) |
| PMD weekly outlook | `data/parsed/pmd/weekly_outlook/latest.json` | 7 | Urdu text; Urdu dates are not parsed |

**253 documents, 1,909 chunks, 0 skipped.** Parsed artifacts that exist but are *not* narrative documents were counted and left out: PMD daily forecast rows (39, structured), SUPARCO campaigns (2, short metadata), FFC reservoir levels (6), AQI observations (371), per-province GLOF rows (2, already covered by the GLOF document).

## Canonical document

`document_id`, `source`, `source_type`, `title`, `document_date` (+ `document_date_text`, `document_date_basis`), `published_at`, `url`, `file_path`, `province`, `admin_unit_id`, `admin_unit_name`, `provinces`, `districts`, `admin_unit_ids`, `geography_status` / `_basis` / `_text`, `event_type`, `event_types`, `event_type_raw`, `language_script`, `raw_text`, `content_sha256`, `metadata`, `ingestion_timestamp`, `parser_version`, `normalization_version`. Anything the source does not state is null: 26 documents have no usable date (21 unparseable, 5 not stated), `published_at` is null everywhere except where a source provides one, `url` exists only for FFC. `ingestion_timestamp` is the source artifact's own parse/retrieval time (so reruns are byte-identical). `raw_text` is stored verbatim.

IDs: `document_id = <source>:<source_type>:<the source's own identifier>` (stable; content changes do not change identity). Dates: only unambiguous forms ("26 June 2026", "1ST DECEMBER 2025", ISO) are parsed; "12.07.2026"-style, garbled or Urdu dates stay null.

## Geography and events

Provinces/districts are resolved with the existing canonical resolver (`scripts/geo`), accepting only exact / alias / normalized matches — no fuzzy matches, caveated seed units (Mangla, Kamra, …) and gauge-station names never become units. The original text is always kept. A single `province`/`admin_unit_id` is set only when exactly one province is established (PDMA daily reports use the issuing authority's jurisdiction, Punjab, with that basis recorded; districts mentioned are resolved separately). Statuses: `resolved`, `resolved_multi`, `partial`, `unresolved`, `not_stated` (current corpus: 42 / 103 / 97 / 0 / 11). Event types come only from source-provided fields (NDMA weather-event keywords, FFC/NDMC hazard topic, PMD alert type), normalized by a small explicit map; PDMA daily reports carry none (108 documents have at least one).

## Chunking and provenance

Verbatim character slices of the document (1,200 chars, 150 overlap, cut on whitespace), never mixing documents. `chunk_id = <document_id>#cNNNN`, with `char_start`/`char_end`, `chunk_sha256`; `raw_text[char_start:char_end] == chunk_text` is validated for every chunk. Evidence records carry document + chunk ids, title, source, date, geography, event, relevance, a verbatim snippet **with its offsets in the document text**, and the source reference (url, file path, content hash).

## Storage

`db/migrations/0029_rag_foundation.{up,down}.sql` (additive, reversible): `rag.documents`, `rag.document_chunks`. Loader: `scripts/rag/build_rag_corpus.py [--load]` (upserts; rows missing from a rebuild get `is_current = false`, nothing is deleted); artifacts in `data/analytics/rag/` (full JSONL gitignored, summary tracked). `rag.documents` / `rag.document_chunks` have no vector column; Task 30 stores embeddings separately in `rag.chunk_embeddings` (below). Neither pgvector nor PostGIS is installed.

## Retrieval and API (Task 29 baseline, Task 30 semantic mode, Task 31 hybrid mode)

`GET /api/v1/rag/search` returns evidence records (document id, chunk id, title, source, date, geography, event, relevance, verbatim snippet with offsets, source reference). Filters (source, source type, province, admin unit, event type, `date_from`/`date_to`) apply to every mode; documents without a date never match a date filter. Other read-only endpoints: `GET /api/v1/rag/documents`, `/documents/{document_id}`, and `GET /api/v1/rag/ask` (below). No write endpoint exists (POST/PUT/PATCH/DELETE answer 405).

| `mode` | Method (`relevance_type`) | What it does |
|---|---|---|
| `lexical` (**default of `/search`, unchanged**) | `lexical_bm25_baseline` | BM25 over chunk text; matches words that literally occur (no synonyms/stemming) |
| `semantic` | `semantic_vector` | embeds the query with the same model that embedded the chunks and ranks chunks by cosine similarity; optional `min_score` (default 0.60) |
| `hybrid` | `hybrid_rrf` | reciprocal rank fusion of the BM25 and semantic result lists (below); `min_score` applies to the semantic side |

Invalid `mode`, or `min_score` with `mode=lexical` -> 422. If the embedding runtime or stored vectors are unavailable, `semantic` and `hybrid` answer 503 with the reason; lexical mode is unaffected. All three retrievers sit behind the same `search(query, filters, limit)` contract (`pipeline/rag/retrieval.py`, `semantic.py`, `hybrid.py`).

### Hybrid strategy (Task 31)

BM25 scores and cosine similarities are on unrelated scales, so scores are never added. Only ranks are fused: `fused = Σ 1/(k + rank)` over the lists that returned the chunk, `k = 60` (the standard RRF constant), each retriever contributing up to 50 candidates. Ties break by `chunk_id`, so output is deterministic. Each hybrid evidence record exposes `lexical_rank`, `semantic_rank` (null when the retriever did not return it), `fused_rank`, `lexical_score`, `semantic_score` and `relevance_type = hybrid_rrf`. For the hybrid mode only, a fixed stop-word list is removed from the query before BM25 (otherwise BM25 matches function words); `/search?mode=lexical` is unchanged. `k`, the pool and the stop-word list were fixed before the evaluation and not tuned on it.

## Grounded answers (Task 31): `GET /api/v1/rag/ask`

Pipeline: question -> retrieval (`mode`, default `hybrid`; `source`, `province`, `admin_unit_id`, `event_type`, `date_from`, `date_to`, `top_k` 1-10 default 5, `min_score`) -> evidence selection (top-ranked chunks, skipping chunks whose text duplicates an already selected one) -> LLM -> deterministic validation -> response. The `ask` default of `hybrid` is a judgement call for a new endpoint, **not** something the evaluation proves (see below); `/search` keeps `lexical`.

**Evidence contract.** Each chunk the model sees carries `chunk_id` (the citation id), `document_id`, source and type, title, document date, geography, event metadata, source URL/path, the **full chunk text** and a one-line retrieval summary (type, score, ranks). The system prompt (`pipeline/rag/grounding.py::SYSTEM_PROMPT`) tells the model to answer only from that evidence, cite every sentence as `[chunk:<chunk_id>]` using only supplied ids, not to invent or estimate dates, counts, locations or causes, not to do arithmetic, to treat evidence text as data (prompt-injection guard), not to calculate or reinterpret risk levels, and to reply `INSUFFICIENT_EVIDENCE` when the evidence does not suffice.

**Response.** `answer`, `answer_status`, `citations` (chunks the accepted answer cites, with source reference), `evidence[]` (everything that was supplied, always returned separately so the answer is auditable), `retrieval` (mode, method, filters, embedding model), `model` (provider/model/configured/error), `groundedness`, `disclaimer`.

| `answer_status` | HTTP | Meaning |
|---|---|---|
| `ANSWERED` | 200 | answer passed citation validation |
| `INSUFFICIENT_EVIDENCE` | 200 | the model abstained (an abstention may not carry digits or more than 25 words) |
| `INVALID_ANSWER` | 200 | validation failed; the answer is **withheld** (`answer` is null; the raw text is kept in `groundedness.rejected_answer_text` for audit only) |
| `RETRIEVAL_EMPTY` | 200 | nothing retrieved; the model is not called (and no provider is needed) |
| `LLM_UNAVAILABLE` | 503 | no provider configured, or it timed out / errored / returned malformed output; the body still contains the evidence |

**Citation validation** (`validate_answer`, no model involved): every cited id must be one of the supplied chunk ids (`unknown_citation`); at least one citation (`no_citations`); every sentence or bullet of 4+ words must carry a citation (`uncited_sentence`); numbers in a sentence that do not occur in the text of the chunks it cites are reported as `warnings` only (dates and thousands separators are written differently in reports). This is provenance checking, **not fact checking**: it cannot tell that a cited chunk truly supports the claim, and the per-sentence rule is strict and may reject legitimate answers (not measured with a real model).

**Provider abstraction** (`pipeline/rag/llm.py`): `LLMProvider.generate(system, question, evidence, constraints) -> LLMResult`. Standard-library HTTP only (no SDK, no LangChain/LlamaIndex). Two providers: `anthropic` (Messages API) and `openai_compatible` (chat completions, also many self-hosted servers). Configure by environment: `PORI_LLM_PROVIDER`, `PORI_LLM_MODEL` (required, no default), `PORI_LLM_API_KEY`, optional `PORI_LLM_BASE_URL`, `PORI_LLM_TIMEOUT` (30 s), `PORI_LLM_MAX_TOKENS` (600). Credentials are read from the environment only, never committed, never logged or echoed in errors. **Current provider: none configured; neither provider has been run against a live endpoint.** CI sets no key: it runs a lexical-only API image, checks that `/ask` answers `RETRIEVAL_EMPTY` (lexical) or 503 (hybrid), and uses mocked providers. An optional live test (`tests/rag/test_llm_live.py`, marker `live_llm`) skips unless `PORI_LLM_*` is set.

The RAG layer computes no risk score and does not interpret `HIGH` / `CRITICAL` / `MODERATE` / `LOW` / `INSUFFICIENT_DATA`; the risk engine stays the authority and the answer text only quotes what evidence states.

The Streamlit page `dashboard/pages/7_RAG_Ask.py` calls `/ask` through `dashboard/api_client.py` and shows the answer, status, citations and retrieved evidence separately; API failures become a friendly message.

## Embeddings (Task 30)

| | |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` (MIT), quantized ONNX build `Qdrant/bge-small-en-v1.5-onnx-Q` |
| Model version | immutable Hugging Face revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55`; weights sha256 `51f1bd0a…f2431` |
| Runtime | fastembed 0.8.1 on ONNX Runtime 1.30.0 (CPU, no PyTorch); `requirements/embeddings.txt` |
| Dimension | 384, L2-normalized (cosine = dot product); queries are embedded without an instruction prefix |
| Corpus embedded | 1,909 of 1,909 chunks, 0 failed (about 19 minutes on the development CPU) |
| Option selected | **A — local model.** No embedding-API credentials exist in the project (no hosted API was used or invented); PyPI and Hugging Face were reachable; 8 CPUs / 7 GB available. |

Why this model: small (67 MB), retrieval-tuned, 512-token input (chunks are ~1,200 characters; longer token sequences are truncated), runs without PyTorch. It is English-only: the 7 Urdu outlook documents (14 chunks) are poorly served semantically and remain reachable through lexical search.

**Vector storage.** `db/migrations/0030_rag_chunk_embeddings.{up,down}.sql`: `rag.chunk_embeddings(chunk_id, model_name, model_version, embedding_dimension, embedding REAL[], normalized, chunk_sha256, metadata, created_at)`, primary key `(chunk_id, model_name, model_version)` so several models/versions coexist and nothing is overwritten; a check keeps the stored dimension equal to the vector length; `chunk_sha256` marks a vector stale if the chunk text changes. **pgvector is not used:** it is not available in the project's `postgres:15` image, and the image was deliberately not changed. Similarity is computed in-process (numpy) over the 1,909 x 384 vectors loaded into memory (about 3 MB) and cached per corpus version — fine at this size, not for hundreds of thousands of chunks.

**Generation.** `scripts/rag/embed_chunks.py` (backend job, never an API request): embeds chunks lacking a vector for the exact model/version (or whose text changed), upserts, reports embedded/failed counts. Re-running embeds nothing and creates no rows; vectors are deterministic for a fixed model and input (compared with a 1e-6 tolerance). `--repair-metadata` fills run metadata without recomputing vectors (needed once: the first run stored empty metadata because the lazily loaded model's info was read before loading; fixed and covered by a regression test). No placeholder vectors exist anywhere in production code.

## Evaluation 1 (Task 30, 16 cases, BM25 vs semantic; real corpus, `config/rag_semantic_eval.yaml`, report in `data/analytics/rag/semantic_eval_report.json`)

16 cases; a chunk is relevant if its verbatim text contains a term of the concept (crude judge; top results are printed in the report for human checking). Paraphrase queries were fixed before any semantic result was seen. Precision@5, lexical vs semantic (threshold 0.60):

| Case (query) | BM25 | Semantic |
|---|---:|---:|
| people who lost their lives | 0.0 | **1.0** |
| destroyed dwellings and residences | 0.0 | **1.0** |
| scorching temperatures across the plains | 0.2 | **0.6** |
| melting ice lake burst threatening villages | 0.4 | **0.6** |
| sudden intense rainfall in a small area | 0.0 | **0.4** |
| rivers bursting their banks | 0.8 | 0.8 |
| mountain slope collapse blocking highways | **0.6** | 0.4 |
| advance notice of severe downpour | **0.2** | 0.0 |
| "what happened in Swat" (place name) | **1.0** | 0.0 |
| "Chitral situation report" | 1.0 | 1.0 |
| source / date filter cases | 0.8-1.0 | 1.0 |
| 3 unsupported queries (finance, sport, recipe) | 5/5/0 junk results | **0 results** |

Paraphrase mean precision@5: semantic 0.60 vs BM25 0.275 (semantic better in 5 of 8, BM25 in 2, 1 tie). Filters were respected in every result of both modes. **Semantic search is not uniformly better:** it missed a rare place name entirely and two advisory/hazard paraphrases. A small dense model is weak on exact proper nouns, which is why lexical stays the default and hybrid scoring is the obvious next step.

**Threshold.** Unrelated queries scored at most 0.584 cosine and real queries' best hits at least 0.617, so the default floor is 0.60. It was chosen on this same small set (in-sample, 3 negative queries) and is a heuristic, not a calibrated probability; single-word queries score lower than sentences.

## Evaluation 2 (Task 31): BM25 vs semantic vs hybrid, 46 cases (`config/rag_semantic_eval.yaml`, report `data/analytics/rag/semantic_eval_report.json`)

The 16 Task 30 cases are unchanged; 30 were added (exact places, districts, provinces, disaster terms, paraphrases, advisory language, casualty language, infrastructure damage, unsupported questions) and frozen before hybrid was run (only the corpus vocabulary was checked so each case can have relevant results). Nothing was tuned afterwards. **This remains a small heuristic evaluation**: substring relevance judge, one run, one author, cases are not independent samples. Precision@5, mean over cases, default 0.60 cosine floor:

| Group (cases) | BM25 | Semantic | Hybrid |
|---|---:|---:|---:|
| exact entity: places, districts, provinces, Swat/Chitral (13) | **0.985** | 0.508 | 0.923 |
| …cases with no relevant result at all | 0 | 5 | 0 |
| paraphrase / advisory / casualty / infrastructure (19) | 0.463 | **0.737** | 0.632 |
| Task 30 paraphrase+advisory subset (8) | 0.275 | **0.600** | 0.475 |
| disaster terms in the report's own words (4) | 1.0 | 1.0 | 1.0 |
| all cases with a relevant answer (39) | 0.728 | 0.708 | **0.790** |
| share of returned results judged irrelevant (39) | 0.272 | 0.220 | **0.210** |
| unsupported questions (7): results returned (any result is junk) | 20 | **5** | 15 |
| …queries that returned junk | 4 | **1** | 3 |

What this shows, plainly:
- **Hybrid is the best single mode on average over supported cases, but it is not uniformly better.** It is at least as good as both single methods in 27 of 39 cases and strictly best in 1 (`rivers_bursting`); it is worse than the better single method in 12: `scorching_heat`, `lives_lost`, `glacier_lake`, `advance_notice`, `geo_swat`, `source_pdma`, `place_quetta`, `para_crops`, `para_evacuation`, `para_bridges`, `cas_injured`, `cas_fatalities`.
- **Swat** (the known semantic failure): hybrid recovers it through BM25 (precision 0.6 vs 0.0 semantic) but not fully (BM25 alone 1.0), because weak semantic hits are interleaved by rank fusion. Same pattern for `place_quetta` (0.4 hybrid, 0.8 BM25).
- **Paraphrase:** semantic alone remains best; hybrid sits between BM25 and semantic. The advisory paraphrase (`advance_notice`) is still weak in every mode.
- **Unsupported queries:** hybrid inherits BM25 junk because BM25 has no relevance floor and matches any rare word (e.g. "earnings", "price"); semantic with its floor is the best at returning nothing, yet still returns junk for a near-domain question (`hurricane damage in Florida`), so a floor is not a guarantee. This is why abstention cannot rely on retrieval alone.
- The RRF constants were not tuned; a lexical relevance floor or a tuned fusion could change these numbers, but doing that on this same set would make the evaluation meaningless, so it is left for a held-out set.

## Evaluation 3 (Task 31): grounded-answer pipeline, development evaluation (`config/rag_grounded_eval.yaml`, `scripts/rag/evaluate_grounded.py`, report `data/analytics/rag/grounded_eval_report.json`)

10 supported and 5 unsupported questions, frozen before running; a development check, not a measure of factual accuracy. **No LLM was available, so model answer quality, hallucination rate and abstention behaviour of a real model were NOT measured.** `--live` exists for when `PORI_LLM_*` is configured. What was measured:

| Measure (top_k = 5) | Lexical | Semantic | Hybrid |
|---|---:|---:|---:|
| supported questions whose evidence contains an expected term (evidence coverage) | 9/10 | 9/10 | **10/10** |
| unsupported questions where retrieval returned nothing (`RETRIEVAL_EMPTY`) | 0/5 | **4/5** | 2/5 |
| evidence chunks returned for the 5 unsupported questions | 25 | **5** | 13 |
| validator probes behaved as designed (valid / unknown id / uncited / abstention) | 10/10 | 10/10 | 10/10 |

The probes are deterministic answers built from the real retrieved chunks (a one-claim excerpt with a correct citation must be `ANSWERED`; with an unknown id or no citation it must be `INVALID_ANSWER`; `INSUFFICIENT_EVIDENCE` is recognised): they test our checks on real chunk ids, not a model. Where retrieval does return junk for an unsupported question, only the model's abstention can prevent an answer, and that was not tested.

## Tests (three tiers)

Unit (no model; a *test-only* stand-in embedder, proves logic not quality): `tests/rag/test_embeddings_unit.py`, `api/tests/test_rag_semantic_api.py`. Database/integration (real PostgreSQL, scratch copy for rollback/idempotency): `tests/db/test_rag_embeddings.py`. Real-model (marker `real_model`; the actual model and stored embeddings, skipped when unavailable): `tests/rag/test_embeddings_real.py`. CI installs no model, so it runs the first tier plus the lexical-only API image, where `mode=semantic` must answer 503; the full tiers run locally.

## Proposal needing approval: pgvector (not done)

pgvector would move similarity search into PostgreSQL (`vector(384)` + HNSW/IVFFlat index) and matters once the corpus grows well beyond ~50k chunks. It requires an image with the extension (for example `pgvector/pgvector:pg15`, same PostgreSQL 15 major version and data layout), because `postgres:15` cannot load it. Impact: replacing the database container image; existing data volume is reused but must be backed up and restore-verified first; slightly larger image; no change to Free Tier/AWS (database is local). Migration: `CREATE EXTENSION vector`, add `embedding_v vector(384)` to `rag.chunk_embeddings`, `UPDATE ... SET embedding_v = embedding::vector`; rollback: drop the column/extension and switch the image back. Recommendation: defer until needed, and decide together with the separate PostGIS image question rather than twice.

## Full local corpus vs Git-tracked CI corpus

The numbers above (253 documents, 1,909 chunks) describe the **full local corpus**: every parsed artifact on the machine that runs the pipeline. `data/parsed/` is gitignored apart from a small set of files committed earlier, so a CI checkout sees a much smaller, intentionally unchanged **CI fixture corpus**: 81 documents / 401 chunks (15 NDMA sitreps, 58 PDMA daily reports, 1 PMD alert, 7 PMD outlook items; no FFC/NDMC documents because `data/parsed/canonical/` is not tracked). The corpus tests adapt to whichever corpus is present and live-database tests skip when no database exists, so CI exercises the logic on the fixture corpus while the exact full-corpus figures are asserted only locally. Parsed data is deliberately not added to git to make CI see 253.

## Limitations

PDMA text is column-interleaved and NDMA text includes table fragments, which also limits embedding quality; Urdu documents are only lexically searchable; 26 documents are undated; the retrievers hold the corpus in memory; consecutive daily reports are not de-duplicated (the `/ask` evidence selector skips identical chunk text only). Retrieval quality was measured on small heuristic sets (46 and 15 cases) with a substring judge. **No real LLM has been run:** answer quality, citation behaviour of an actual model, abstention and hallucination rates are unmeasured, and the strict per-sentence citation rule may reject good answers. Citation validation proves provenance, not truth; the number check is a warning, not a gate. Hybrid retrieval passes BM25 junk on some unsupported queries. Evidence text comes from scraped documents and is passed to a model with an instruction to treat it as data; this reduces but does not eliminate prompt-injection risk. Do not present answers as official warnings.

## Next step

Configure an LLM provider (a credential/provider decision is the owner's), run `scripts/rag/evaluate_grounded.py --live` and the live test, and measure faithfulness, citation accuracy and abstention on a larger held-out question set before relying on answers. Then consider a lexical relevance floor or tuned fusion evaluated on that held-out set, pgvector (still a proposal needing approval, below) only if the corpus grows, and per-claim citation checking.
