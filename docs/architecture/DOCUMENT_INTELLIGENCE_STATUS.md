# Document intelligence & RAG — status (Tasks 29 and 30)

**Task 29 (implemented):** a traceable document/chunk store with provenance, a deterministic keyword (BM25) retriever and a read-only evidence API.
**Task 30 (implemented):** real text embeddings of every chunk, vector storage in PostgreSQL, and an optional semantic retrieval mode behind the same API.
**Not implemented:** LLM generation, answer synthesis, summarization, agentic workflows, automatic reasoning. The API returns *source evidence*, not answers. This is a retrieval layer, not an AI assistant.

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

## Retrieval and API (Task 29 baseline + Task 30 semantic mode)

`GET /api/v1/rag/search` returns evidence records (document id, chunk id, title, source, date, geography, event, relevance, verbatim snippet with offsets, source reference). Filters (source, source type, province, admin unit, event type, `date_from`/`date_to`) apply to both modes; documents without a date never match a date filter. Other read-only endpoints: `GET /api/v1/rag/documents`, `/documents/{document_id}`. No write endpoint exists.

| `mode` | Method (`relevance_type`) | What it does |
|---|---|---|
| `lexical` (default, unchanged) | `lexical_bm25_baseline` | BM25 over chunk text; matches words that literally occur (no synonyms/stemming) |
| `semantic` | `semantic_vector` | embeds the query with the same model that embedded the chunks and ranks chunks by cosine similarity; optional `min_score` (default 0.60) |

Invalid `mode` or `min_score` with `mode=lexical` -> 422. If the embedding runtime or stored vectors are unavailable, `mode=semantic` answers 503 with the reason; lexical mode is unaffected. Both retrievers sit behind the same `search(query, filters, limit)` contract (`pipeline/rag/retrieval.py`, `pipeline/rag/semantic.py`); there is no hybrid scoring.

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

## Evaluation (real corpus, `config/rag_semantic_eval.yaml`, report in `data/analytics/rag/semantic_eval_report.json`)

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

## Tests (three tiers)

Unit (no model; a *test-only* stand-in embedder, proves logic not quality): `tests/rag/test_embeddings_unit.py`, `api/tests/test_rag_semantic_api.py`. Database/integration (real PostgreSQL, scratch copy for rollback/idempotency): `tests/db/test_rag_embeddings.py`. Real-model (marker `real_model`; the actual model and stored embeddings, skipped when unavailable): `tests/rag/test_embeddings_real.py`. CI installs no model, so it runs the first tier plus the lexical-only API image, where `mode=semantic` must answer 503; the full tiers run locally.

## Proposal needing approval: pgvector (not done)

pgvector would move similarity search into PostgreSQL (`vector(384)` + HNSW/IVFFlat index) and matters once the corpus grows well beyond ~50k chunks. It requires an image with the extension (for example `pgvector/pgvector:pg15`, same PostgreSQL 15 major version and data layout), because `postgres:15` cannot load it. Impact: replacing the database container image; existing data volume is reused but must be backed up and restore-verified first; slightly larger image; no change to Free Tier/AWS (database is local). Migration: `CREATE EXTENSION vector`, add `embedding_v vector(384)` to `rag.chunk_embeddings`, `UPDATE ... SET embedding_v = embedding::vector`; rollback: drop the column/extension and switch the image back. Recommendation: defer until needed, and decide together with the separate PostGIS image question rather than twice.

## Full local corpus vs Git-tracked CI corpus

The numbers above (253 documents, 1,909 chunks) describe the **full local corpus**: every parsed artifact on the machine that runs the pipeline. `data/parsed/` is gitignored apart from a small set of files committed earlier, so a CI checkout sees a much smaller, intentionally unchanged **CI fixture corpus**: 81 documents / 401 chunks (15 NDMA sitreps, 58 PDMA daily reports, 1 PMD alert, 7 PMD outlook items; no FFC/NDMC documents because `data/parsed/canonical/` is not tracked). The corpus tests adapt to whichever corpus is present and live-database tests skip when no database exists, so CI exercises the logic on the fixture corpus while the exact full-corpus figures are asserted only locally. Parsed data is deliberately not added to git to make CI see 253.

## Limitations

PDMA text is column-interleaved and NDMA text includes table fragments, which also limits embedding quality; Urdu documents are only lexically searchable; 26 documents are undated; the retrievers hold the corpus in memory; consecutive daily reports are not de-duplicated; semantic quality was measured on a 16-case set with a crude term judge; no hybrid ranking, re-ranking or query expansion exists.

## Next step (LLM answer generation)

Add a generation layer that takes the evidence records returned by `/api/v1/rag/search` (start with `mode=semantic`, consider hybrid with BM25 first because of the place-name weakness), passes only those chunks to an LLM, and returns an answer that cites `chunk_id`s and refuses when retrieval returns nothing above threshold. It needs an LLM provider/credential decision, a groundedness/citation evaluation set, and must not be added to the read-only evidence endpoint without an explicit design.
