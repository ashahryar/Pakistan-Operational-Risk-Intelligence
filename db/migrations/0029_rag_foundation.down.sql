-- Task 29 rollback: removes ONLY the objects created by 0029_rag_foundation.up.sql.
DROP TABLE IF EXISTS rag.document_chunks;
DROP TABLE IF EXISTS rag.documents;
DROP SCHEMA IF EXISTS rag;     -- raises (and aborts the rollback transaction) if anything else lives in it
