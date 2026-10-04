-- Task 33 rollback: removes ONLY the ml schema objects created by 0033 (no other schema or table is touched).
DROP TABLE IF EXISTS ml.predictions;
DROP TABLE IF EXISTS ml.model_runs;
DROP SCHEMA IF EXISTS ml;
