# Tier-1 national data parsing status (Task 19)

Raw (Task 15, read-only) → `scripts/parsing/tier1/*` parser → `pipeline/canonical/tier1_adapters.py` → geography enrichment (Task 18) → DQ (`validate_record`) → canonical JSONL in `data/parsed/canonical/<domain>/tier1_<dataset>.jsonl`. Source-specific parsed output is in `data/parsed/tier1/<source>/`. Regenerate everything with `python scripts/parsing/tier1/run_tier1.py [--no-db]` (byte-identical on re-run; `data/raw` and manifests are never written). Machine-readable counts: `data/parsed/tier1/coverage_report.json`.

## Coverage (actual counts from the acquired files)

| Dataset | Raw files | Parsed | Failed | Not in scope | Records extracted → unique | Canonical | Geo resolved | Ambiguous | Unresolved | Quarantined |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| SUPARCO DisasterWatch | 4 | 2 | 0 | 2 | 4 → 2 | 2 (`hazard_alert`) | 0 | 0 | 0 (2 have no location) | 0 |
| EPA Punjab AQI | 6 | 6 | 0 | 0 | 795 → 408 (37 district names + 350 daily + 21 station) | 371 (`air_quality_observation`) | 371 | 0 | 0 | 0 |
| FFC reservoir levels | 3 | 3 | 0 | 0 | 9 → 6 | 6 (`reservoir_observation`) | not attempted (6) | – | – | 0 |
| FFC DFSR / GLOF | 17 | 11 | 4 | 2 | 15 → 9 | 9 (7 `document`, 2 `hazard_alert`) | 2 | 0 | 0 (7 documents not attempted) | 4 |
| PMD / NDMC bulletins | 13 | 8 | 0 | 5 | 8 → 4 | 4 (`document`) | not attempted (4) | – | – | 0 |

"Not in scope" = files intentionally not parsed (listing HTML pages; SUPARCO `global-themes.json`). Duplicate retrievals of the same file collapse by stable `source_record_id`, earliest retrieval wins. Quarantine rows are written to `data/parsed/tier1/quarantine.jsonl` by default (a DB insert per run would multiply on re-runs); `--db-quarantine` uses the real `dq.quarantine` via `write_quarantine`. With Postgres reachable, `admin_unit_id` is populated from the real `geo.admin_unit` (read-only); e.g. all 371 AQI records carry Lahore's id.

## Per dataset

**SUPARCO — parsed (partial by design).** `campaigns-live.json` → two campaigns (Monsoon 2026, Nepal Floods 2026) as `hazard_alert`: alert level → `severity` (source's own value), `starts_at/ends_at/last_updated` → `valid_from/valid_until/issued_at`. `hazard_type` comes only from an explicit GLIDE prefix (`FL-` → flood); the Nepal campaign has no GLIDE number so its hazard stays null (not inferred from the name). No location field exists, so no geography. `global-themes.json` is a map-layer catalogue with no hazard observations: not parsed. Limitation: the source is a live snapshot of two campaigns — no hazard *events*, no coordinates, no earthquake/landslide/GLOF/etc. content exists in the acquired data.

**EPA Punjab AQI — parsed.** Station snapshot (Lahore, 10 stations/snapshot; pollutants arrive as numeric strings → numbers, `null` stays null — e.g. Safari Park `pm25`), 350 daily city-level AQI values (2025-10-01 → 2026-09-15), and the 37-name district list (reference data, not canonicalized; 32/37 resolve, unresolved: Muzaffargarh, Nankana Sahib, Pakpattan, Talagang, Vehari). Limitations: the snapshot has no measurement timestamp, so `observed_at` is the retrieval time and is labelled `observed_at_basis=retrieved_at`; no pollutant units or AQI category are stated by the source, so none are asserted; the calendar carries no pollutant values; only Lahore station data was acquired; no city field exists (never inferred).

**FFC reservoir — parsed.** One homepage sentence yields Tarbela/Mangla/Chashma level (ft) and live storage (MAF) for 2026-09-15 06:00 and 2026-09-16 06:00 (naive time, no timezone stated), plus the combined live storage. The source spells Tarbela "Tarble"; the original is kept in `reservoir_name_original`. No inflow/outflow/capacity exist on the page. Geography is deliberately not attempted: the reservoir name "Mangla" would otherwise match the Task 10 district entry "Mangla" (a documented non-district) — a false mapping.

**FFC DFSR/GLOF — partial.** The PDFs' text layer has OCR-style recognition noise, so river/gauge statuses and figures are not structured and stay in the narrative `text`. Extracted reliably: DFSR report date from the dateline (6 reports: 2026-07-01, 07-02, 07-03, 09-04, 09-07, 09-08); GLOF alert issue time (2026-06-27 09:00) and the two provinces its opening paragraph names (Gilgit-Baltistan, Khyber Pakhtunkhwa → two `hazard_alert`, both resolved). **Blocked:** `DFSR-05-09-2026.pdf` (54 chars), `DFSR.-06-09-2026.pdf` (0) and `Press-Release-29-06-2026.pdf` (0, in both retrieval folders) are image-only scans; OCR is not available, so they are quarantined as `no_text_layer` (4 files) — no content fabricated.

**PMD/NDMC — parsed as documents.** Four bulletins (three English, one Urdu-script) become `document` records with the full extracted text (future RAG source). Title only where a heading line says bulletin/report/outlook/review (1 of 4: "FORTNIGHTLY DROUGHT BULLETIN", period 2026-01-01 → 2026-01-15). `publication_date` is never invented; the PDF CreationDate is kept separately as `pdf_creation_date`. The Urdu PDF's text is extracted in visual/garbled order — preserved as-is, flagged `script=arabic`. `2.pdf` (source-side 404) was never acquired. No rainfall/temperature values are structured from narrative text.

## Canonical / Spark

New canonical domains: `reservoir_observation`, `document` (plus existing `air_quality_observation` and `hazard_alert`). `contracts.py` now also rejects: resolved-without-key / id-without-resolved status, and reservoir unit violations (must be ft / MAF). `normalize_timestamp` no longer turns a date-only value into a midnight timestamp. Task 18 Spark: explicit schemas and silver typing were added for the four Tier-1 domains inside the existing `databricks/src/{common,silver}` modules (no new Spark architecture); provenance schema gained `source_file/retrieved_at/sha256`. Spark/Delta code is not executed here (pyspark not installed) — only schema registration is tested.

## Known blockers / limitations

Image-only FFC PDFs need OCR; DFSR figures need a better text source than the OCR layer; SUPARCO exposes no event-level data; EPA station data covers Lahore only and has no measurement time; the NDMC Urdu bulletin needs RTL-aware extraction; nothing is persisted to PostgreSQL and no DAG runs these parsers (by design for this task).
