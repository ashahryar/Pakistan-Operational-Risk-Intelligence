# RAG Foundation — Design Document (Task 16A, ADR-0001)

> **Update (Task 32):** the risk engine and the RAG layer are now combined by `/api/v1/intelligence/ask` (computed context and documents kept separate; see the status page).
> **Earlier update (Tasks 29-31):** hybrid retrieval and a grounded, citation-validated answer endpoint now exist (no LLM has been run yet; see the status page).
> **Earlier update (Tasks 29-30):** the document/chunk/provenance store, a lexical retriever, real embeddings
> (local ONNX model, vectors in PostgreSQL `REAL[]`, no pgvector) and an optional semantic search mode now exist — see
> [`DOCUMENT_INTELLIGENCE_STATUS.md`](DOCUMENT_INTELLIGENCE_STATUS.md). LLM generation is still **not**
> implemented; the design below remains the target.

**Status: DOCUMENTED ONLY. No code, no embeddings, no vector store,
no LLM integration exists yet.** This document exists so a future task
has a concrete, honest starting contract instead of inventing one
under time pressure — per Task 16A's explicit instruction not to build
a RAG system in this task.

## Why RAG, and why not yet

PORI already has a large corpus of official documents it has acquired
but never made queryable in natural language: 731+ NDMA/PDMA/PMD PDFs
under `data/raw/`, plus Task 15's newly-acquired SUPARCO/AQI
Punjab/FFC/PMD-NDMC artifacts under `data/raw/manifests/`. A future
"ask a question about flood risk in Rajanpur, cited to the actual
sitrep" capability is a real, valuable PORI goal — but it requires a
working geography foundation (have: Task 10/11), a working document
corpus with real provenance (have: Task 15's manifests), and a
working PostgreSQL instance with pgvector (do not have yet). Building
the retrieval/generation loop before those exist would mean building
it against fabricated or placeholder data, which CLAUDE.md rule 7
forbids in spirit even for a "foundation."

## Target architecture

```
Official documents (data/raw/*, already acquired by Task 15 + legacy extractors)
        |
        v
Document extraction (scripts/parsing/common/pdf_reader.py -- REUSE, not reimplement)
        |
        v
Chunking (structure-aware: don't shred tables mid-row -- not implemented)
        |
        v
Metadata attachment (see schema below)
        |
        v
Embeddings (model choice not yet made -- see "Open decisions")
        |
        v
Vector store: PostgreSQL + pgvector
        |         (same database as everything else -- one database to
        |          run, back up, and secure; not a second search
        |          cluster; revisit only past ~5M vectors)
        v
Retrieval (hybrid: pgvector similarity + metadata filter, e.g.
        |  "flood risk in Rajanpur" filters to Rajanpur's geo.admin_unit
        |  P-code before ranking -- reuses the existing geography
        |  foundation, doesn't invent a second one)
        v
LLM (provider/model not yet chosen)
        |
        v
Cited answer (mandatory -- see "Citation is not optional" below)
```

## Chunk metadata contract

Every chunk stored in the (not-yet-created) vector table must carry,
at minimum:

| Field | Source | Notes |
|---|---|---|
| `chunk_id` | generated | stable, deterministic (e.g. hash of document_id + chunk index) |
| `document_id` | Task 15 manifest `sha256`, or a new ID for legacy-extractor documents | ties back to `dq.source_document`-equivalent lineage |
| `source_organization` | Task 15 manifest `source_organization`, or extractor source | e.g. "ndma", "pdma", "ffc" |
| `document_title` | extracted from the PDF/report, or the filename if none | never fabricated if absent -- `NULL`, not a guessed title |
| `document_date` | extracted report date where parsers already capture one (e.g. NDMA `report_date`) | `NULL` if genuinely unknown, never defaulted to ingestion date |
| `publication_date` | if the source publishes one distinctly from the report date | often the same as `document_date`; kept separate because they can differ |
| `geography` | resolved via the existing `geo.admin_unit`/`geo.name_alias` resolver (Task 10), never a raw free-text string | `NULL`/`unresolved` is a valid, honest value |
| `hazard_type` | flood / drought / earthquake / heatwave / AQI / etc., where the source already classifies it | not inferred by the embedding step itself |
| `document_type` | sitrep / advisory / bulletin / press-release / DFSR / GLOF-alert / weekly-outlook / etc. | mirrors the classification already present in Task 15's manifests (`classification` field) |
| `source_url` | Task 15 manifest `source_url`, or the extractor's known source URL | |
| `chunk_text` | the actual chunk content | |
| `chunk_index` | position within the document | for reconstructing order / adjacent-chunk context |

## Citation is not optional

Every answer this system ever produces must cite the specific
document(s) and chunk(s) it drew from. A response with no citation is
a refusal, not an answer — matching the "Do not implement a fake
chatbot that invents answers" instruction. Concretely, once built:

- The LLM prompt template will require inline citation markers per
  claim, resolved against the actual retrieved chunk metadata (not
  the model's own training knowledge).
- Any question the retrieval step returns no relevant chunks for is
  answered with an explicit "no matching source document found," never
  a best-effort guess.
- A future evaluation set (curated Q&A pairs with known-correct
  citations) is how citation accuracy will be measured before this is
  considered trustworthy enough to expose to a real user — not
  self-reported by the model.

## Open decisions (deliberately not made in this task)

- Embedding model choice (local vs. hosted; dimensionality) — affects
  the pgvector column definition, so this is a real decision, not a
  detail, and is deferred to the task that actually builds this.
- Chunking strategy specifics (fixed-size vs. structure-aware
  section/table boundaries) — PDF table extraction already exists
  (`scripts/parsing/common/pdf_table_reader.py`); a real chunker
  should reuse it rather than re-shredding tables as flat text.
- LLM provider/model.
- Whether legacy (pre-Task-15) `data/raw/ndma/`, `data/raw/pdma/`,
  `data/raw/pmd/` documents get backfilled into this corpus, or only
  new Task-15-style acquisitions are indexed going forward.

## What this task did NOT do

- No `pgvector` extension was enabled on the database.
- No embedding was computed.
- No document was chunked.
- No LLM was called.
- No new Python package was added for this purpose.
- No database schema change was made (Part M of Task 16A: schema
  changes require a stop-and-report, and none was genuinely required
  to write this document).
