# Bronze layer schema contracts

**Status: documented contract, no table implemented.** Each planned
bronze table (see `databricks/README.md`) is schema-on-read from the
existing `data/raw/` / `data/parsed/` JSON produced by
`scripts/extraction/` and `scripts/acquisition/` — this directory
documents the intended Delta table schema for each, so a future
implementation has a contract to build against instead of inventing
field names ad hoc.

## Common columns (every bronze table)

| Column | Type | Source |
|---|---|---|
| `_source` | string | the organization ("ndma", "pdma", "pmd", "epa_punjab", "ffc", "suparco") |
| `_source_document` | string | the raw file path this record was built from |
| `_ingested_at` | timestamp | when this record was written to bronze (not when the source was scraped) |
| `_parser_version` | string | carried through unchanged from the existing parser's `PARSER_VERSION` constant |

## Example: `bronze_ndma_sitreps`

Schema-on-read from `data/parsed/ndma/sitreps/*.json` (produced by
`scripts/parsing/parse_ndma.py`). Column names mirror that JSON's
existing top-level keys exactly (`report_number`, `report_date`,
`casualties`, `damage`, `relief`, `rescue`, `validation`) — no
renaming happens at bronze.

## Example: `bronze_pdma_gauge`

Schema-on-read from `data/parsed/pdma/gauge/<year>/*.json` (produced
by `scripts/parsing/parse_gauge.py`). Column names mirror
`report_datetime`, `gauges` (array of `{station, river,
current_level_ft, danger_level_ft, discharge_cusecs, flow_status}`).

## Example: `bronze_aqi_punjab`

Schema-on-read from Task 15's `data/raw/epa_punjab/aqi_punjab/<date>/*.json`.
Unlike the other bronze tables, this one reads the *raw* (unparsed)
acquisition JSON directly — no parser exists yet for this Tier 1
source (Task 15 explicitly stopped at raw acquisition).

The remaining planned bronze tables follow the same pattern: mirror
the existing parser/acquisition output's real field names, add the
four common columns above, no transformation.
