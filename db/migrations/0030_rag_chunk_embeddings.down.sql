-- Task 30 rollback: removes ONLY rag.chunk_embeddings (rag.documents / rag.document_chunks and everything else are untouched).
DROP TABLE IF EXISTS rag.chunk_embeddings;
