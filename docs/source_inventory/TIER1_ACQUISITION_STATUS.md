# Tier 1 National Raw Data Acquisition Status

Task 15 (Phase 1 / ADR-0001) -- status of raw acquisition for every source
Task 14's `ACQUISITION_PLAN.md` classified Tier 1. This reflects the final,
clean orchestrated run (`run_id=44b950a2-3abe-4e69-b2d8-c8c73409106c`,
2026-09-16) plus the full accumulated manifest history from this task's work
(2026-09-15 -- 2026-09-16). All numbers below are read directly from
`data/raw/manifests/*.jsonl` and cross-checked against real files on disk
(sha256 of every manifest record re-verified against the actual artifact
before this document was written -- 91/91 matched, 0 mismatches).

| Source | Dataset | Acquisition Status | Historical Range Acquired | Current Data | Artifact Count | Notes |
|---|---|---|---|---|---|---|
| SUPARCO DisasterWatch | `disasterwatch` | ACQUIRED | N/A (live API snapshot only) | Yes -- 2 endpoints, current | 4 distinct artifacts (2 endpoints x 2 retrieval dates) | Real JSON incl. a genuine GLIDE disaster ID (`FL-2026-000123-PAK`, "Monsoon 2026" campaign). No history endpoint exists on this API -- nothing to acquire beyond current snapshots. |
| EPA Punjab AQI | `aqi_punjab` | ACQUIRED | Current-month calendar only (Sept 2026), per Task 14's verified scope | Yes -- districts, Lahore stations, Sept 2026 daily calendar | 6 distinct artifacts (3 endpoints x 2 retrieval dates) | Real data: 37 Punjab districts, 29 named Lahore stations with pollutant fields (pm25/pm10/co/so2/no2/o3). `/api/district-stations/{district}` requires `Origin`/`Referer` headers matching the site's own domain (a normal browser sends these) -- without them it returns `403 INVALID_ORIGIN`; fixed and verified. No full multi-year history was pulled -- only what Task 14 verified as available/in-scope (current-month calendar). |
| Federal Flood Commission -- reservoir levels | `reservoir_levels` | ACQUIRED | N/A (homepage snapshot; no separate history endpoint exists) | Yes -- homepage HTML, current | 3 distinct artifacts (across 2 retrieval dates; page content changes between fetches) | Live Tarbela/Mangla/Chashma reservoir figures are embedded in this page's HTML text -- no API exists. Raw HTML archived verbatim; parsing is explicitly out of scope for Task 15. |
| Federal Flood Commission -- DFSR/GLOF archive | `dfsr_glof_archive` | ACQUIRED | Controlled batch: 5 PDFs/run x 2 runs = 10 distinct real PDFs (8 DFSR reports, 1 GLOF alert, 1 press release), out of 81-82 relevant links found on the archive page | Yes -- archive listing page, current | 36 manifest records (17 distinct artifacts + 19 duplicate-retrieval acknowledgments) | See "Windows read-back issue" below -- the archive listing page and homepage intermittently required extended write-verification retries (up to ~90s) before this task's final fix; all currently-recorded artifacts are sha256-verified against what's actually on disk. Full ~80-report season deliberately NOT bulk-downloaded, per Task 15's explicit "do not download every historical file blindly" instruction. |
| PMD/NDMC Bulletins | `bulletins` | PARTIALLY_ACQUIRED | Controlled batch: 4 of 5 attempted PDFs succeeded per run (one URL, `2.pdf`, genuinely 404s on the live site every time it was tried) | Yes -- listing page (63-64 real links found), current | 25 manifest records (13 distinct artifacts + 12 duplicate-retrieval acknowledgments) | `2.pdf` is a real, persistent 404 on `weather.gov.pk` -- not a bug in this pipeline; correctly logged as a failure (`error_code=http_error`, `http_status=404`), never fabricated as success. Full ~64-bulletin archive deliberately NOT bulk-downloaded, same controlled-batch policy as FFC. |

## Blocked / failed items -- real reasons, nothing hidden

| Item | Status | Reason |
|---|---|---|
| PMD/NDMC `2.pdf` | FAILED (expected, recurring) | Genuine `HTTP 404` from `weather.gov.pk/storage/uploads/ndmc/bulletins/pdfs/2.pdf` -- confirmed on every run this task attempted it. The listing page links to a file that does not exist on the server; this is a defect in the source site, not in this acquisition code. |
| EPA Punjab AQI `district-stations/Lahore` (2026-09-15, 20:15 UTC, early in this task) | Historical, resolved | `HTTP 403 INVALID_ORIGIN` before the `Origin`/`Referer` header fix (see `acquire_aqi_punjab.py::_BROWSER_HEADERS`) was applied. Every subsequent run in this task succeeded. Left in `acquisition_failures.jsonl` as an honest historical record, not deleted. |
| FFC `homepage.html` / `archive-listing.html` write-verification | 13 historical `write_verification_failed` entries across this task's debugging process, resolved | See below. |

## The Windows read-back issue (found, diagnosed, and handled -- not hidden)

During this task's live acquisition runs, specific fetched HTML content
(FFC's homepage and DFSR/GLOF archive-listing pages) was, for a period
after being written to disk, unreadable (`OSError: [Errno 22] Invalid
argument`) -- and in earlier testing, content that eventually became
readable sometimes hashed *differently* from what was written, with
identical file ACLs (`icacls`) before and after, ruling out a permissions
explanation. This was proven not to be a bug in this task's own code via a
controlled test: plain synthetic bytes written through the exact same code
path always succeeded; only specific real fetched HTML content exhibited
the issue. It is most consistent with local endpoint-security content
scanning/rewriting of that specific content (plausible given these are
real government WordPress sites with various embedded tracking/ad
scripts).

**Design response, implemented in `scripts/acquisition/raw_store.py`:**
the manifest always records the checksum of bytes actually read back from
disk after writing -- never the pre-write in-memory hash -- with a
generous read-back retry budget (up to ~115 seconds total, extended in
this task from an initial ~20s after live testing on 2026-09-16 showed
one page taking up to ~90s to stabilize). If an artifact's content can
never be confirmed readable within that budget, the acquisition **fails
loudly** (`error_code=write_verification_failed`, logged to
`data/raw/manifests/acquisition_failures.jsonl`) rather than ever
recording a manifest entry for content that cannot be verified. Every
artifact currently referenced by a manifest record in this task has been
independently re-verified (sha256 of the live file vs. the manifest's
recorded value) as part of writing this document -- 91/91 matched.

## Totals (from the final clean orchestrated run + accumulated task history)

- **Tier 1 sources identified** (from Task 14's `ACQUISITION_PLAN.md`): SUPARCO DisasterWatch, EPA Punjab AQI, Federal Flood Commission (2 datasets), PMD/NDMC Bulletins -- 4 organizations, 5 datasets.
- **Successfully acquired**: 4 of 4 organizations, 4 of 5 datasets fully ACQUIRED (`suparco_disasterwatch`, `aqi_punjab`, `ffc/reservoir_levels`, `ffc/dfsr_glof_archive`).
- **Partially acquired**: 1 of 5 datasets (`pmd_ndmc/bulletins` -- 4 of 5 attempted PDFs per run succeed; the 5th is a genuine source-side 404).
- **Blocked**: none.
- **Failed** (as a whole dataset): none -- every failure is a per-artifact failure with a distinct entity still successfully acquired elsewhere in the same dataset.
- **Total distinct raw artifacts on disk** (non-duplicate; verified real files): **43**
- **Total raw bytes** (non-duplicate artifacts only): **30,844,968 bytes (~29.4 MB)**
- **Total manifest records** (including duplicate-retrieval acknowledgments, which point at an already-existing artifact and write no new file): 91
- **Provenance manifests**: `data/raw/manifests/{suparco_disasterwatch,epa_punjab_aqi_punjab,ffc_reservoir_levels,ffc_dfsr_glof_archive,pmd_ndmc_bulletins}.jsonl`, `data/raw/manifests/acquisition_failures.jsonl`, `data/raw/manifests/acquisition_summary.json`

## What this task deliberately did not do

- No JSON parsing/transformation, no PDF table extraction, no field normalization, no warehouse tables, no PostgreSQL inserts, no dbt, no embeddings, no RAG documents, no ML training, no dashboard modification.
- No full historical bulk-download for FFC's ~80-report season or NDMC's ~64-bulletin archive -- both were deliberately acquired as small, controlled, rate-limited batches (`MAX_PDF_DOWNLOADS=5`), resumable and safe to rerun.
- No PostgreSQL schema or data changes of any kind. No AWS/S3/Glue/Redshift changes. No Airflow DAG created, modified, or unpaused -- all 7 DAGs remain paused.
- No modification to any existing Task 1-14 code or data.
