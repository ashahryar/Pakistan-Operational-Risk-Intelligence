-- Task 30 -- embedding storage for the RAG chunks (additive, idempotent).
-- pgvector is NOT available in the project's postgres:15 image and the image is deliberately not changed, so vectors are stored
-- as REAL[] (float4 array). The row shape is the vector-store contract: a later move to pgvector is
-- `ALTER ... ADD COLUMN embedding_v vector(<dimension>)` + `UPDATE ... SET embedding_v = embedding::vector`.
-- Never touches rag.documents / rag.document_chunks rows or any other existing table.
-- Rollback: 0030_rag_chunk_embeddings.down.sql

CREATE TABLE IF NOT EXISTS rag.chunk_embeddings (
    chunk_id             TEXT NOT NULL REFERENCES rag.document_chunks(chunk_id),
    model_name           TEXT NOT NULL,                 -- e.g. BAAI/bge-small-en-v1.5
    model_version        TEXT NOT NULL,                 -- immutable revision of the exact weights used
    embedding_dimension  INTEGER NOT NULL CHECK (embedding_dimension > 0),
    embedding            REAL[] NOT NULL,               -- produced by the model above; never a placeholder
    normalized           BOOLEAN NOT NULL,              -- unit-length vector (cosine similarity == dot product)
    chunk_sha256         TEXT NOT NULL,                 -- hash of the chunk text this vector was computed from (staleness check)
    metadata             JSONB NOT NULL DEFAULT '{}',   -- runtime/library versions, weights hash
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, model_name, model_version),  -- one embedding per chunk per model/version; other models coexist
    CHECK (cardinality(embedding) = embedding_dimension)
);
CREATE INDEX IF NOT EXISTS ix_rag_embeddings_model ON rag.chunk_embeddings (model_name, model_version);
