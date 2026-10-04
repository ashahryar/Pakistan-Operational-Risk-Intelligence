# Document intelligence & RAG foundation — status (Task 29)

**Implemented: Phase A — a traceable document/chunk store and a deterministic *keyword* retriever that returns source evidence.**
**Not implemented: embeddings, vector search, any LLM, answer generation.** This is not yet "semantic RAG".

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

`db/migrations/0029_rag_foundation.{up,down}.sql` (additive, reversible): `rag.documents`, `rag.document_chunks`. Loader: `scripts/rag/build_rag_corpus.py [--load]` (upserts; rows missing from a rebuild get `is_current = false`, nothing is deleted); artifacts in `data/analytics/rag/` (full JSONL gitignored, summary tracked). No vector column: no embedding model exists and neither pgvector nor PostGIS is installed.

## Retrieval and API

`pipeline/rag/retrieval.py`: BM25 over chunk text (`lexical_bm25_baseline`), filters for source, source type, province, admin unit, event type and date range applied before ranking; IDF is corpus-wide, results are deterministic. Documents without a date never match a date filter. This matches words that literally occur; it does not understand synonyms, stems or translations ("inundation" will not find "flood"). Read-only endpoints: `GET /api/v1/rag/documents`, `/documents/{document_id}`, `/search` (evidence, no generated answer). The retriever holds the corpus in memory (~2k chunks), rebuilt when the corpus changes.

## Limitations

Keyword-only; PDMA text is column-interleaved and NDMA text includes table fragments; Urdu documents are searchable only by exact Urdu words; 26 documents are undated; only 11 documents (FFC/NDMC) have no geography; the in-memory retriever is a baseline that will not scale past tens of thousands of chunks; document text is not de-duplicated across consecutive daily reports.

## Next step (Phase B)

Choose an embedding model, add a pgvector (or equivalent) column/table keyed by `chunk_id` (+ model name/version), embed the existing chunks, and add a retriever implementing the same `search(query, filters, limit)` contract; then a generation layer that answers only from retrieved evidence and cites `chunk_id`s.
