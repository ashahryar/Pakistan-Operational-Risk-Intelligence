# Repository cleanup report (Task 40)

Method: for every candidate, search the tracked tree (`git grep`) for imports, DAG references, Docker references, test references and documentation references; delete only when nothing live uses it. Data, quarantine, analytics outputs, evidence registries, configs and tests were not touched.

## Deleted (21 files, all via `git rm`, recoverable from history)

| File | Why it was safe to delete | Evidence |
|---|---|---|
| `pipeline/utils/duplicate_checker.py` | empty file (0 bytes) | no importer; mentioned only in CLAUDE.md and the audit |
| `pipeline/utils/metadata_logger.py` | empty file | same |
| `scripts/extraction/common/utils.py` | empty file | no importer |
| `scripts/warehouse/load_dimensions.py`, `load_facts.py`, `warehouse_models.py` | empty files of the never-executed warehouse scaffold | no importer; the non-empty warehouse scripts are kept (documented scaffolding) |
| `pipeline/utils/script_runner.py` | divergent duplicate of `pipeline/helpers/script_runner.py`, which is the only one any DAG imports | no import of `pipeline.utils.script_runner` anywhere; flagged "DUPLICATE, delete" in the Task 16 audit |
| `scripts/database/create_pdma_tables.py` | mislabelled: it is an old PDMA *loader* (not DDL) that the README told users to run; the live loader is `load_pdma.py` | no importer, no DAG, no test; the README reference was removed |
| `scripts/parsing/test_cleaner.py`, `test_pdf.py`, `test_tables.py` | manual print-scripts, not tests (pytest only collects `tests/`) | no importer, no DAG, no test |
| `dashboard/components/{header,executive_cards,executive_summary,footer,sidebar,filters}.py`, `dashboard/sections/{hydrology,weather}.py`, `dashboard/charts/{hydrology_charts,weather_charts}.py` | the old Home composition. Home was rebuilt (Task 40) and no module imports them any more (`git grep` over `dashboard/` and `tests/`); they carried the invented "platform health" and "flood risk 100/100" logic | no importer anywhere; `components/alerts.py` was trimmed to the one function still used |

The matching 21 rows were removed from `docs/architecture/codebase_audit.csv` so the audit stays consistent with the tree (its validation tests pass).

## Examined and deliberately kept

| Item | Reason |
|---|---|
| `scripts/database/load_ndma_v2.py` | referenced by `tests/database/test_legacy_loader_safety.py`, which guards that legacy loaders stay unable to truncate |
| `scripts/warehouse/*` (non-empty), `scripts/risk_engine/` | documented unused scaffolding; removing it is a design decision deferred by CLAUDE.md |
| `pipeline/sensors/` | unused but documented; part of the sensor story in the README |
| `pori_airflow_backup.dump` (repo root) | a local database backup; git-ignored (`*.dump`), never committed, must not be deleted |
| `databricks/`, `aws/`, `infrastructure/`, `db/`, `common/` | each is referenced by code, tests or documentation |
| scratch helper scripts from Tasks 38 and 39 (`edit_yaml.py` and similar) | were created under the session scratchpad, never inside the repository, so there is nothing to delete |

## Generated outputs

Gitignored regenerable outputs (for example `data/analytics/risk/gold_operational_risk.jsonl`) stay ignored. The unrelated `data/...` modifications that predate Task 39 are unchanged and unstaged.
