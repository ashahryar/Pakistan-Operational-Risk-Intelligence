# Canonical parsing and normalization

Task 17 adds a post-parser contract layer at `pipeline/canonical/`. It does not alter Task 8 parser outputs or database loaders. Adapters consume parsed NDMA, PDMA and PMD records and produce deterministic JSONL suitable for `data/parsed/canonical/<domain>/` and future Spark/Delta Bronze-to-Silver work.

Supported adapters are NDMA disaster situation-report casualty, damage and rescue rows; PDMA rainfall and gauge rows; and PMD daily forecasts, weekly outlooks and weather alerts. The contracts also define weather, rainfall, gauge, disaster, hazard-alert and air-quality domains. Tier-1 Task 15 artifacts remain raw-only: SUPARCO, EPA Punjab AQI, FFC and PMD/NDMC need dedicated parsers before adapters can honestly emit records.

Strings are trimmed/collapsed while originals are retained in source fields. Safe numeric forms (including commas) are parsed; `N/A` and `-` become null, never zero. Recognized dates become ISO values; naive source times remain naive rather than being misrepresented as UTC. Units are explicit and only known aliases are normalized.

Every record carries source, deterministic source-record ID, source document/path, parser and normalization versions, and ingestion timestamp. The Task 10 resolver is reused for exact/alias/normalized/fuzzy/ambiguous/unresolved outcomes. Pure adapters retain a canonical admin-unit key and resolution status; a DB-backed consumer may look up the existing `geo.name_alias` / `geo.admin_unit` ID without guessing. Ambiguous and unresolved locations are never forced into a district.

Canonical validation uses the existing quarantine writer when supplied: invalid records are written to `dq.quarantine` with `canonical_invalid` rather than silently dropped. The writer sorts records and JSON keys, so a repeat with identical input is byte-identical. No database migration, S3 change, live Databricks workspace, RAG component, or FastAPI change is part of this layer.
