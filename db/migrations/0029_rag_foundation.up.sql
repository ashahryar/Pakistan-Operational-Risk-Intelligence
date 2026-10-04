-- Task 29 -- document intelligence / RAG foundation, Phase A (additive, idempotent).
-- Adds schema `rag` with rag.documents and rag.document_chunks. No vector column: no embedding model exists yet and pgvector
-- is not installed, so nothing is faked. Never alters geo.*, risk.*, dq.* or any existing table.
-- Rollback: 0029_rag_foundation.down.sql

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.documents (
    document_id          TEXT PRIMARY KEY,                  -- <source>:<source_type>:<source's own id>, stable across reruns
    source               TEXT NOT NULL,
    source_type          TEXT NOT NULL,
    title                TEXT,
    document_date        DATE,                              -- NULL when the source states none / it is unparseable
    document_date_text   TEXT,
    document_date_basis  TEXT,
    published_at         TEXT,                              -- only if the source publishes one (kept as text)
    url                  TEXT,
    file_path            TEXT,
    province             TEXT,                              -- only when exactly one province is established
    admin_unit_id        INTEGER REFERENCES geo.admin_unit(id),
    admin_unit_name      TEXT,
    provinces            JSONB NOT NULL DEFAULT '[]',
    districts            JSONB NOT NULL DEFAULT '[]',       -- [{raw, name, admin_unit_id, status}] original text always kept
    admin_unit_ids       JSONB NOT NULL DEFAULT '[]',
    geography_status     TEXT NOT NULL CHECK (geography_status IN ('resolved', 'resolved_multi', 'partial', 'unresolved', 'not_stated')),
    geography_basis      TEXT,
    geography_text       JSONB NOT NULL DEFAULT '[]',
    event_type           TEXT,                              -- only when the source gives exactly one
    event_types          JSONB NOT NULL DEFAULT '[]',
    event_type_raw       JSONB NOT NULL DEFAULT '[]',
    language_script      TEXT,
    raw_text             TEXT NOT NULL,                     -- verbatim, never rewritten
    content_sha256       TEXT NOT NULL,
    metadata             JSONB NOT NULL DEFAULT '{}',
    ingestion_timestamp  TEXT,                              -- the source artifact's own parse/retrieval time
    parser_version       TEXT,
    normalization_version TEXT NOT NULL,
    is_current           BOOLEAN NOT NULL DEFAULT TRUE,     -- FALSE = absent from the latest build (never deleted)
    loaded_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rag_documents_source ON rag.documents (source, source_type) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_rag_documents_date ON rag.documents (document_date) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_rag_documents_admin_unit ON rag.documents (admin_unit_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS ix_rag_documents_provinces ON rag.documents USING GIN (provinces);
CREATE INDEX IF NOT EXISTS ix_rag_documents_events ON rag.documents USING GIN (event_types);

CREATE TABLE IF NOT EXISTS rag.document_chunks (
    chunk_id         TEXT PRIMARY KEY,                      -- <document_id>#cNNNN
    document_id      TEXT NOT NULL REFERENCES rag.documents(document_id),
    chunk_index      INTEGER NOT NULL,
    char_start       INTEGER NOT NULL,                      -- verbatim slice: documents.raw_text[char_start:char_end] = chunk_text
    char_end         INTEGER NOT NULL,
    chunk_text       TEXT NOT NULL,
    chunk_sha256     TEXT NOT NULL,
    chunker_version  TEXT NOT NULL,
    is_current       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (document_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS ix_rag_chunks_document ON rag.document_chunks (document_id) WHERE is_current;
