# Acquisition Plan — Pakistan Operational Risk Intelligence

**Phase 1 / Task 14 (ADR-0001).** This is a blueprint, not an implementation. No ingestion code, DAG, or schema change is created by this document — it is what a future Task 15/16 would execute against. Built directly on the verified findings in [`HISTORICAL_COVERAGE_MATRIX.md`](HISTORICAL_COVERAGE_MATRIX.md) and [`NATIONAL_SOURCE_INVENTORY.md`](NATIONAL_SOURCE_INVENTORY.md).

---

## Tier 1 — Acquire first

High-value, reliable, accessible, and directly useful for PORI's operational-risk purpose. All four are `VERIFIED` (not merely `ARCHIVE_PAGE_VERIFIED`) in the coverage matrix.

| Dataset | Why Tier 1 |
|---|---|
| **SUPARCO DisasterWatch API** | The only real, working, multi-hazard government API found in this entire research effort (7 hazards: flood, GLOF, earthquake, landslide, forest fire, cyclone, drought). JSON, not PDF — the lowest-friction acquisition method of anything in either inventory. |
| **AQI Punjab API** | Real, working JSON API; 37 districts, station-level granularity (finest in the whole inventory); fills a data family (air quality) the platform has zero coverage of. |
| **Federal Flood Commission — DFSR + live reservoir text** | Two real seasons of daily flood reports (2024, 2026) plus plain-HTML live reservoir levels for Tarbela/Mangla/Chashma — easier to scrape than IRSA's PDF-only equivalent for the same reservoirs. |
| **Federal Flood Commission — GLOF Alerts** | The only verified, dated, government GLOF archive found — closes a named data-family gap directly. |
| **PMD/NDMC Bulletins** | 64-entry, ~18-month verified archive; the only verified drought data source anywhere in the inventory. |

## Tier 2 — Acquire after Tier 1

Useful, but more difficult, lower-priority, or dependent on further verification before a real acquisition plan can be written.

| Dataset | Why Tier 2 |
|---|---|
| **IRSA Daily Data** | Genuinely valuable (reservoir data complementing PDMA gauge data) but PDF-only, shallow confirmed public history (~1 week rolling), and internal table structure unverified — needs a follow-up session that actually opens a PDF before scraping is designed. |
| **FFC Annual/Damages Reports, Archives (footer nav)** | Nav items confirmed real; content, format, and depth not yet opened. |
| **PMD Seismic Monitoring (`seismic.pmd.gov.pk`)** | A real, distinct PMD subdomain confirmed to exist; not yet browsed. |
| **PMD TCWC (cyclone)** | Official body confirmed; no advisory archive was visible at the time of research (no active cyclone) — needs a re-check during an active cyclone advisory period, or a direct search for a TCWC bulletin archive URL. |

## Tier 3 — Reference only

Useful for maps/context/RAG but not worth automated ingestion initially.

| Dataset | Why Tier 3 |
|---|---|
| **PMD/NDMC Dam Reservoirs widget** | Live values exist but are not extractable as text (client-rendered widget); reservoir set overlaps IRSA/FFC. |
| **PMD/NDMC Satellite Indices (LST/NDVI/TVDI)** | Real imagery products, but raster/image format, not structured data. |
| **PDMA Balochistan MHVRA (9 district reports)** | Genuine risk-assessment PDFs, static/one-off, Drive-hosted — valuable as reference documents (e.g. a future RAG corpus), not as a recurring ingestion feed. |
| **PDMA Balochistan Contingency Plans** | Same reasoning — static reference documents. |
| **Provincial Irrigation Departments (4)** | Named only via a cross-link; not yet independently verified to contain anything acquirable. |

## Do Not Acquire Automatically

| Dataset | Why |
|---|---|
| **PDMA Balochistan "Daily Weather Reports & Advisory Alerts" / "Daily situation reports" headings** | Deep-verified this session and found to link to exactly **one** example document each, not a recurring archive. Building a scraper against a homepage heading that isn't backed by a real listing would silently produce a single-document "pipeline" that looks like it's running but never grows — exactly the kind of quiet failure `CLAUDE.md` rule 5 exists to prevent. |
| **PMD/NDMC SPI/SPEI/Outlook maps** | Format and access method entirely unverified (`Unknown / Requires verification` across the board) — acquiring before verification risks the same silent-fabrication risk. |

Nothing above is deleted from either inventory — every row remains in `historical_coverage.csv` with its real `verification_status`, so a future session can pick up exactly where this one left off.

---

## Historical targets (per the task's framework — targets, not assumptions)

| Data family | Target framework | What was actually found |
|---|---|---|
| Disaster/Event data (FFC DFSR/GLOF, SUPARCO campaigns) | 2015–current | Verified depth is **2024–current** for FFC, and only the live window for SUPARCO (historical/non-live campaigns not yet queried) — well short of 2015; deeper history was not found, not assumed. |
| Weather/Rainfall (PMD forecasts, already ingested) | 1–2 years operational + deeper where reliable | Already matches: repo's live ingestion is current/live; no deeper PMD station archive was located this session. |
| River/Gauge (IRSA, FFC reservoirs) | Current + recent operational history, deeper where accessible | IRSA's *public* history is confirmed shallow (~1 week); FFC's live reservoir text has no archive at all — "deeper where accessible" does not currently apply to either. |
| Climate (PMD/NDMC) | Long-term where PMD provides it | NDMC Bulletins reach 18 months (Jan 2025–Jul 2026) — real, but not "long-term" in the sense of a multi-year climate record; no multi-year PMD climate dataset was located this session. |
| Situation reports (NDMA, PDMA, FFC) | ~2015–current where archives exist | Verified depths found: NDMA (current season only, this archive view), PDMA Punjab/KP/Sindh (2025–2026), FFC (2024, 2026) — **no source in either inventory was confirmed to reach back to 2015.** This is stated plainly rather than padded to match the target. |
| Hazard maps / MHVRA / Contingency plans | Acquire relevant historical versions | NDMA (8 districts), PDMA Balochistan (9 districts) MHVRA; PDMA KP Contingency Plans 2012–2026 (Task 13) are the deepest static archives found across both tasks. |

**Honest conclusion:** the 2015–current disaster-data target is **not currently achievable** from any source verified in this project. The realistic near-term acquisition window, based only on what was actually confirmed, is **2024–current** for event/flood data (FFC, PDMA archives) and **2025–current** for drought/AQI data (NDMC, AQI Punjab).

---

## Data volume estimates (explicitly estimates, ranges used, never fabricated precision)

| Dataset | Files | Records | Storage | Growth |
|---|---|---|---|---|
| SUPARCO DisasterWatch | N/A (API) | 2 live campaigns now; unknown historical count | Unknown | Event-driven, unpredictable |
| AQI Punjab | N/A (API) | Order of ~1,000–5,000 station-days/month province-wide (37 districts x multiple stations each, not individually summed) | Unknown | Continuous, daily |
| FFC DFSR | ~70–90 PDFs/monsoon season (estimate from ~70 confirmed for the partial 2026 season through mid-September) | N/A (documents, not rows) | Unknown, likely low (PDF, small) | ~1 season/year |
| FFC GLOF Alerts | ~3–10/year (estimate from 3 confirmed in a partial 2026 season) | N/A | Unknown | Event-driven |
| NDMC Bulletins | ~40–50/year (estimate from 64 confirmed across ~18 months) | N/A | Unknown, likely low (PDF) | Continuous |
| IRSA Daily Data | ~365/year if daily (not confirmed beyond the visible 8-day window) | N/A | Unknown | Daily (if the pattern holds) |

All figures above are **estimates derived from partial-season counts actually observed**, not full-year totals — marked as such deliberately, per the task's instruction never to present an estimate as a fact.

---

## Freshness requirements (verified update behavior only)

| Dataset | Verified freshness |
|---|---|
| SUPARCO DisasterWatch | Event-driven / live (`last_updated` timestamps observed within hours-to-days of the check) |
| AQI Punjab | Sub-daily (a 24-hour historical endpoint exists; a live "Current AQI" tab is present) |
| FFC live reservoir levels | At least daily (explicit "0600 Hours" timestamp on the homepage) |
| FFC DFSR | Daily |
| NDMC Bulletins | Weekly (weather updates); monthly/fortnightly/quarterly (drought bulletins) — mixed cadence within one archive |
| IRSA Daily Data | Daily (assumed from the rolling-window pattern; not confirmed beyond the visible week) |
| PMD/NDMC Satellite Indices | Irregular, roughly every 2–4 weeks (observed gap between dated entries, not a stated schedule) |

---

## Final acquisition order

1. **SUPARCO DisasterWatch API**
   - *Why first:* real JSON API already confirmed working with zero scraping/PDF-parsing needed; single highest-value, lowest-friction source found across both tasks.
   - *Historical range:* only the live window confirmed (2026-06 → 2026-09); non-live campaign depth unknown.
   - *Current range:* live, `last_updated` within days.
   - *Extraction method:* direct HTTP GET against documented JSON endpoints (no scraping library needed beyond what the project already uses).
   - *Expected volume:* small per campaign (5–12 resources observed); total historical volume unknown until the non-`live` endpoint is queried.
   - *Destination:* a new source-specific bronze layer, following the existing `data/raw/<source>/` convention — not implemented in this task.
   - *Dependencies/blockers:* none identified; a follow-up query without `live=true` is the immediate next research step, not a blocker.

2. **AQI Punjab API**
   - *Why second:* second real JSON API, fills a completely uncovered data family (air quality), finest verified geographic granularity of the entire inventory.
   - *Historical range:* at least Oct 2025 → current confirmed.
   - *Current range:* live.
   - *Extraction method:* direct HTTP GET against `/api/districts`, `/api/district-stations/{district}`, `/api/aqi-calendar-data`.
   - *Expected volume:* moderate — 37 districts x multiple stations each x daily.
   - *Destination:* new `aqi` domain under the existing raw/parsed convention.
   - *Dependencies/blockers:* pollutant-level (PM2.5/PM10/etc.) field names not yet enumerated — a short follow-up query needed before schema design.

3. **Federal Flood Commission — live reservoir levels (homepage text)**
   - *Why third:* trivially scrapable (plain HTML text, no PDF parsing), directly extends the platform's existing river/reservoir coverage.
   - *Historical range:* none (live only).
   - *Current range:* live, ~daily.
   - *Extraction method:* HTML scrape of the homepage's reservoir-level text block.
   - *Expected volume:* 3 reservoirs x 1 reading, refreshed at least daily.
   - *Destination:* extends the existing PDMA-gauge-adjacent domain, or a new `ffc_reservoirs` table.
   - *Dependencies/blockers:* none identified.

4. **Federal Flood Commission — DFSR + GLOF Alert archive**
   - *Why fourth:* same site/pattern as #3, but requires PDF parsing (higher effort than the plain-text reservoir levels).
   - *Historical range:* 2024, 2026 confirmed (~70+ reports/season each).
   - *Current range:* daily, current.
   - *Extraction method:* web scrape (year-grouped archive page) + PDF download/parse, matching the existing PDMA Punjab scraper pattern.
   - *Expected volume:* ~70–90 DFSR PDFs/season + a handful of GLOF alerts/season.
   - *Destination:* new `ffc` domain, following the existing `scripts/extraction`/`scripts/parsing` convention.
   - *Dependencies/blockers:* the 2025-labelled archive URL showing 2026 content should be re-checked before building a year-parameterized scraper, to avoid the same URL-vs-content mismatch this session observed.

5. **PMD/NDMC Bulletins**
   - *Why fifth:* real, deep (18-month), verified archive; closes the platform's drought-data gap entirely.
   - *Historical range:* Jan 2025 → Jul 2026.
   - *Current range:* current (most recent bulletin within the archive's own listing).
   - *Extraction method:* web scrape (searchable/paginated DataTable) + PDF download.
   - *Expected volume:* ~64 documents observed; continues growing weekly/monthly.
   - *Destination:* new `pmd_ndmc_drought` domain.
   - *Dependencies/blockers:* none identified; mixed cadence (weekly/monthly/fortnightly/quarterly) needs a `frequency`/`interval` field in any future schema, not just a date.

Everything past #5 (IRSA, FFC footer archives, PMD Seismic, PMD TCWC, all Tier 2/3 items) requires the additional verification work named in `HISTORICAL_COVERAGE_MATRIX.md` before an acquisition order can honestly be assigned — recorded as open follow-up work, not silently skipped.
