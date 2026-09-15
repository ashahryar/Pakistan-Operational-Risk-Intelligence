# Historical Coverage Matrix — Pakistan Operational Risk Intelligence

**Phase 1 / Task 14 (ADR-0001).** Extends [`NATIONAL_SOURCE_INVENTORY.md`](NATIONAL_SOURCE_INVENTORY.md) (Task 13) with deeper verification of the sources Task 13 explicitly flagged as unresolved, plus first-pass research into cyclone, GLOF, and landslide data families. This document does not replace the Task 13 inventory — it is a second, deeper pass over a subset of it.

**Companion machine-readable file:** [`historical_coverage.csv`](historical_coverage.csv) — 17 rows, validated by `tests/source_inventory/test_historical_coverage.py`.

**Research date:** 2026-09-16, live browsing session against real production sites and APIs.

**Verification-status legend used throughout (per task instruction — never overstate):**
- `ARCHIVE_PAGE_VERIFIED` — the listing/archive page itself was opened and its real content read.
- `FILES_VERIFIED` — an actual document/file's content was opened and read.
- `HISTORICAL_RANGE_VERIFIED` — earliest/latest dates were confirmed by paging to the actual boundary of an archive (not inferred).
- `FEED_VERIFIED` — a live JSON/API feed was queried and its actual response body read.
- `FEED_NOT_VERIFIED` — a feed/dashboard was seen to exist but its underlying data was not confirmed.

---

## The single most important finding of this task

Two genuine, working, government-hosted **JSON REST APIs** were discovered and directly queried this session — something no part of Task 13 or this platform's existing scrapers has ever used:

1. **SUPARCO DisasterWatch** (`saccs.sgs-suparco.gov.pk/disasterwatch/api/...`) — multi-hazard (flood, GLOF, earthquake, landslide, forest fire, cyclone, drought), with live campaign data including a real GLIDE disaster identifier (`FL-2026-000123-PAK`) and country/province/district administrative vector-tile layers.
2. **AQI Punjab** (`aqi.punjab.gov.pk/api/...`) — 37 Punjab districts, with real per-station daily historical data (e.g. 29 named stations confirmed for Lahore alone) reaching back to at least October 2025.

Both were confirmed by directly navigating to the API endpoint URLs and reading the actual JSON response bodies — not inferred from a dashboard's existence, per this task's explicit instruction not to treat a dashboard as proof of downloadable data.

---

## Summary matrix (required format)

All 17 rows below are drawn directly from [`historical_coverage.csv`](historical_coverage.csv); sections A–F and the granularity/hazard sections further down give the full evidence and caveats behind each row.

| Organization | Dataset | Hazard/Data Family | Earliest Verified | Latest Verified | Historical Depth | Current/Live | Geography | Format | Access | Estimated Volume | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| IRSA | Daily Data (reservoir/river situation) | River/Reservoir | Unknown | 2026-09-15 | Rolling ~8-day window only | Live/current | National (Indus system) | PDF | Manual download | Unknown | P1 |
| PMD / NDMC | Bulletins (Weekly/Monthly/Fortnightly/Quarterly Drought) | Drought | 2025-01 | 2026-07 | 64 entries, ~18 months | Recent + current | National | PDF + image | Web scrape + download | ~64 documents | P1 |
| PMD / NDMC | Dam/Reservoir levels (5 named) | Drought/River | Unknown | 2026-09-15 | No archive, live only | Live/current | National (5 reservoirs) | Web widget | Dashboard only | Unknown | P2 |
| PMD / NDMC | Satellite Indices (LST/NDVI/TVDI) | Drought | 2026-05-06 | 2026-09-15 | ~12 dated entries observed | Live/current | National | Image/raster | Dashboard/map | Unknown | P3 |
| PMD / NDMC | SPI/SPEI/Outlook/Hazard maps, Advisory/Alerts | Drought | Unknown | Unknown | Unknown | Unknown | National | Unknown | Unknown | Unknown | P4 |
| PDMA Balochistan | Daily Weather DSR + Heatwave Advisory (single examples) | Weather/Heatwave | 2025-04 | 2025-09 | 2 documents, no archive | Static | Balochistan | PDF (Drive-hosted) | Manual download | 2 documents | P4 |
| PDMA Balochistan | Contingency Plans (Monsoon/Winter) | Contingency Planning | 2024 | 2026 | 3 documents | Static | Balochistan | PDF (Drive-hosted) | Manual download | 3 documents | P3 |
| PDMA Balochistan | MHVRA district reports | Risk Assessment | 2021 | 2023 | 9 documents (corrected from Task 13's 6) | Static | Balochistan (district) | PDF (Drive-hosted) | Manual download | 9 documents | P2 |
| SUPARCO | DisasterWatch (SACRED System) | Flood, GLOF, Earthquake, Landslide, Forest Fire, Cyclone, Drought | 2026-06-01 | 2026-09-02 | Only live campaigns checked (2 found) | Live/current, real API | National + international | JSON API + MVT tiles | Real REST API | 2 live campaigns | P0 |
| EPA Punjab (AQI Punjab) | AQI Dashboard/API | Air Quality (AQI) | 2025-10 | 2026 (live) | ≥11 months confirmed | Live + recent history | Punjab (37 districts) | JSON API | Real REST API | 37 districts x multi-station | P0 |
| Federal Flood Commission | Daily Flood Situation Reports (DFSR) | Flood | 2024-07-01 | 2026-09-15 | 2 seasons, ~70+ reports/season | Live/current | National | PDF | Web scrape + download | ~70+ PDFs/season | P0 |
| Federal Flood Commission | Live reservoir levels (homepage text) | River/Reservoir | Unknown | 2026-09-15 | No archive, live only | Live/current | National (3 reservoirs) | HTML text | Web scrape | N/A | P1 |
| Federal Flood Commission | GLOF Alerts | GLOF | 2026-06-27 | 2026-07-27 | 3 dated alerts (2026 only checked) | Recent/event-driven | National | PDF | Web scrape + download | 3 (2026) | P1 |
| Federal Flood Commission | Annual/Damages Reports, Archives | Flood/Damage | Unknown | Unknown | Unknown | Static | National | Unknown | Unknown | Unknown | P2 |
| PMD Seismic Monitoring | National Seismic Monitoring / Seismicity Maps | Earthquake | Unknown | Unknown | Unknown | Unknown | National | Unknown | Unknown | Unknown | P3 |
| PMD TCWC | TCWC Early Warning Center | Cyclone | Unknown | Unknown | No archive found | Unknown | National/maritime | HTML | Unknown | Unknown | P2 |
| Provincial Irrigation Depts. (4 provinces) | Not independently visited | River/Irrigation | Unknown | Unknown | Unknown | Unknown | Provincial | Unknown | Unknown | Unknown | P4 |

---

## A. IRSA — Daily Data

| Field | Finding |
|---|---|
| Official URL | `http://pakirsa.gov.pk/DailyData.aspx` |
| Verification status | **PARTIALLY_VERIFIED** — `ARCHIVE_PAGE_VERIFIED` only |
| Actual table content | **FEED_NOT_VERIFIED** — each day's link (e.g. `Doc/Data15-09-2026.pdf`) triggered a browser file-download dialog rather than rendering; PDF content was not opened this session |
| Historical depth | Only a **rolling ~8-day window** of dated links observed (08–15 Sep 2026). No archive, year selector, or pagination was found for this specific listing — a materially different (shallower) picture than assumed after Task 13 |
| Current freshness | Live/current — today's date (15 Sep 2026) present |
| Geographic coverage | National (Indus system); station/reservoir names not confirmed from page content this session (Tarbela/Mangla/Chashma reported by an earlier web search only, not independently re-verified) |
| Format | PDF |
| Access | Manual download, one PDF per day |
| Notes | A `Login` nav item exists — some content may be access-restricted beyond the public rolling window. `Links With Ministries` on this same page independently confirmed the Federal Flood Commission and four provincial Irrigation Departments (Punjab, Sindh, KP, Balochistan) as real, named cross-linked organizations — none of which were visited this session. |
| **Determined priority** | **P1** — genuinely valuable if content can be parsed, but demoted from an assumed-deep source to one with confirmed-shallow (1-week) public history and unconfirmed internal structure. |

---

## B. PMD / NDMC — Drought

| Sub-product | URL | Depth verified | Format | Priority |
|---|---|---|---|---|
| **Bulletins** | `weather.gov.pk/ndmc/bulletins` | **HISTORICAL_RANGE_VERIFIED**: 64 total entries, Jan 2025 → Jul 2026 (~18 months), confirmed by paging a searchable DataTable to its final page (`Showing 61 to 64 of 64 entries`) | PDF (real file paths seen, e.g. `/storage/uploads/ndmc/bulletins/pdfs/week4(June2026).pdf`) + JPG front-page image | **P1** |
| **Dam Reservoirs** | `weather.gov.pk/ndmc/dam-reservoirs/Khanpur` | `ARCHIVE_PAGE_VERIFIED`, live-timestamped (15 Sep 2026 06:31 AM); 5 named reservoirs (Khanpur, Rawal, Simly, Tarbela, Mangla) | Web widget — numeric Level/Flow values rendered client-side, `FEED_NOT_VERIFIED` (not extractable as text) | P2 |
| **Satellite Indices** | `weather.gov.pk/ndmc/satellite-indices/indices` | `ARCHIVE_PAGE_VERIFIED`: ~12 dated Land Surface Temperature entries, 06 May 2026 → 15 Sep 2026; NDVI and TVDI listed in nav but not opened | Image/raster | P3 |
| **SPI/SPEI Maps, Outlook Maps, Drought Hazard/Frequency Maps, Precipitation Forecast, Advisory/Alerts** | `weather.gov.pk/ndmc/spi-maps/map` and sibling paths | Page loads confirmed real (map selector visible); no map content, format, or cadence verified | Unknown / Requires verification | P4 |

**Determination:** NDMC Bulletins is the only NDMC sub-product with a genuinely deep, verified, dated archive. The rest are real pages with unconfirmed underlying content — recorded honestly as such rather than assumed comparable in depth.

---

## C. PDMA Balochistan — deep verification

The task's caution — *"do not assume a homepage heading means a historical archive exists"* — was directly tested and **confirmed true** for this source:

| Section heading | What was actually found |
|---|---|
| "BALOCHISTAN DAILY WEATHER REPORTS & ADVISORY ALERTS" | Exactly **one** linked document (`Monsoon_Weather_DSR_PDMA_Balochistan_08 September_2025.pdf`) — not an archive |
| "Daily Weather Advisory Of Balochistan" | Exactly **one** linked document (heatwave advisory, 11-04-2025) — not an archive |
| "Monthly Seismic reports of Balochistan" | Heading text only — **no link at all** found attached to it |
| MHVRA Reports | A genuine collection — **9 district reports** confirmed by individually distinct filenames (Chaghai, Kachhi, Nushki, Sibi, Quetta, Lasbela, Gwadar, Nasirabad, Jhal Magsi). This corrects Task 13's count of 6 — a more exhaustive link search this session found 3 more. |
| Contingency Plans | 3 real documents confirmed (Monsoon 2024, Monsoon 2025-26, Winter 2024-25) |

**Conclusion:** PDMA Balochistan has real, single example documents and a genuinely useful MHVRA collection, but **no verified recurring report archive** for weather/situation data — this is a materially different (more limited) picture than a reader might assume from the homepage's section headings alone.

---

## D. SUPARCO / DisasterWatch

| Field | Finding |
|---|---|
| Official status | **Confirmed official** — the link was found on SUPARCO's own domain (`suparco.gov.pk`), not merely from a search result as in Task 13 |
| Actual accessible URL | `http://disasterwatch.sgs-suparco.gov.pk/` → redirects to `https://saccs.sgs-suparco.gov.pk/disasterwatch/` ("DisasterWatch - SACRED System") |
| Available hazards | **7 confirmed via real icon asset filenames**: flood, GLOF, earthquake, landslide, forest fire, cyclone, drought (`flood-transparent.png`, `glof-transparent.png`, `eq-transparent.png`, `Landslide_transparent.png`, `forestfire-transparent.png`, `cyclone-transparent.png`, `drought-transparent.png`) |
| Historical coverage | Only the `live=true` filter was queried this session, returning 2 campaigns: **"Monsoon 2026"** (`glide_number: FL-2026-000123-PAK`, starts 2026-06-01, 12 resources) and **"Nepal Floods 2026"** (international, 5 resources, `last_updated: 2026-09-02`). Non-live/historical campaigns were **not enumerated** — true historical depth is an open question. |
| Current/live availability | **FEED_VERIFIED** — real JSON responses read directly from `/disasterwatch/api/resources/campaigns?live=true` |
| Geography | **FEED_VERIFIED**: country/province/district administrative vector-tile layers (`/disasterwatch/api/data-gateway/mvt/{country,provinces,districts}/{z}/{x}/{y}.pbf`) — no tehsil-level layer was observed |
| Format | JSON API + Mapbox Vector Tiles (MVT/PBF) + image assets |
| Download/API access | **Yes — a real, working REST API**, confirmed by directly fetching and reading multiple endpoint responses |
| Access restrictions | None encountered this session for the endpoints queried; whether historical (non-live) campaigns require different access was not tested |

**Determination: P0, Tier 1.** This is the strongest single finding across both Task 13 and Task 14 — a real government API spanning seven hazard families the platform currently has zero coverage of, including the two hardest-to-find (GLOF, cyclone).

---

## E. EPA Punjab — AQI

| Field | Finding |
|---|---|
| Actual feed | **Confirmed real, working JSON API** at `aqi.punjab.gov.pk/api/*` — not the `epd.punjab.gov.pk` department site itself (which remained largely unverifiable due to JS-heavy rendering, consistent with Task 13's finding) |
| Stations | **FEED_VERIFIED**: `/api/district-stations/Lahore` and `/api/historical/24hours?station=...` returned real, named stations — 29 distinct station names appear in one calendar-day response for Lahore alone (e.g. Kahna Nau, Multan Road, Safari Park, GT Road, Egerton Road, Model Town, Punjab University, DHA Phase 5, Johar Town, Gulberg III, Thokar Niaz Baig, and more) |
| Pollutants | Not independently itemized this session — the calendar endpoint returns an aggregate daily `aqi` value and `stationCount`; per-pollutant (PM2.5/PM10/etc.) breakdown was not queried |
| Timestamps | **HISTORICAL_RANGE_VERIFIED**: `/api/aqi-calendar-data?year=2026&month=8&district=Lahore` returned real daily data keyed under `2025 → 10` (October 2025) in the response actually observed |
| Geography | **FEED_VERIFIED**: `/api/districts` returned **37 named Punjab districts** |
| Historical depth | At least October 2025 → present confirmed by an actual API response; earliest possible date not exhaustively probed |
| Refresh frequency | A `/api/historical/24hours` endpoint confirms sub-daily granularity is tracked; a live "Current AQI" tab is also present |
| API/feed/download availability | **Yes — a real, working REST API**, confirmed by directly fetching and reading multiple endpoint responses (`/api/districts`, `/api/district-stations/{district}`, `/api/aqi-calendar-data`, `/api/historical/24hours`) |
| Estimated volume | Not computed precisely this session; order-of-magnitude only — see `historical_coverage.csv` notes |

**Determination: P0, Tier 1.** The finest verified geographic granularity of any source in either inventory (named station, within named district), with a real, queryable historical API.

---

## F. Federal Flood Commission (FFC)

| Field | Finding |
|---|---|
| Official website | **Confirmed**: `https://ffc.gov.pk/` |
| Flood reports | **HISTORICAL_RANGE_VERIFIED**: Daily Flood Situation Reports (DFSR) confirmed for two seasons — **2024** (from 01-07-2024, `ffc.gov.pk/post-monsson-activities/`) and **2026** (01-07-2026 → 15-09-2026, ~70+ dated entries, `ffc.gov.pk/dfsr-glof-press-release-2025/` — note this URL's slug says "2025" but its rendered title and content are "2026"; recorded as an observed site inconsistency, not assumed data) |
| Historical flood information | Footer navigation confirms `ANNUAL FLOOD REPORTS`, `DAMAGES REPORT`, `DAMAGES IN A COUNTRY YEAR 2022`, `ARCHIVES` — **not opened this session**, `UNVERIFIED` |
| River/flood data | **FEED_VERIFIED (as plain text)**: the homepage itself displays live reservoir levels in real numbers — *"Tarble Level 1542.97 feet (Live storage 5.176 MAF) Mangla Level 1219.60 feet ... Chashma Level 646.60 feet ..."* — dated "15, September 2026 @ 0600 Hours" |
| GLOF data | **HISTORICAL_RANGE_VERIFIED**: 3 distinct, dated GLOF alerts confirmed in the 2026 archive (27-06-2026, 11-07-2026, 27-07-2026) — the only verified, dated, government GLOF alert archive found in this entire research effort |
| Maps | Not located/opened this session |
| Annual reports | Nav item confirmed (`ANNUAL FLOOD REPORTS`); not opened |
| Geographic coverage | National; named reservoirs (Tarbela, Mangla, Chashma) and named nullahs (e.g. "Nullah Lai" — cross-references PMD's "Alerts (FFWS Lai)" flash-flood system found in Task 13) |
| Formats | PDF (DFSR, GLOF alerts), plain HTML text (homepage reservoir levels) |
| Acquisition feasibility | **High** — the homepage reservoir-level text is genuinely easier to scrape than IRSA's PDF-only equivalent for the same three reservoirs; the DFSR/GLOF archive pages are plain, real, dated HTML link lists suitable for a scraper matching the existing PDMA Punjab pattern |

**Determination: P0, Tier 1.** Alongside SUPARCO and AQI Punjab, this is the third major upgrade this task produced — Task 13 had marked FFC entirely `Unknown`; it is now the platform's best-verified flood/GLOF source.

---

## Geographic granularity — what was actually confirmed this session

Per the task's explicit instruction not to infer finer granularity from a report title, here is what was **directly observed**, not assumed:

| Source | Finest granularity actually confirmed | How it was confirmed |
|---|---|---|
| AQI Punjab | **Station**, within named **district** (37 districts) | Real JSON API response (`/api/districts`, `/api/district-stations/Lahore`) |
| SUPARCO DisasterWatch | **District** (admin boundary vector-tile layer) | Real JSON API response listing `country`/`provinces`/`districts` MVT layers; no tehsil layer present |
| Federal Flood Commission | **Reservoir / named nullah** (not a formal administrative unit) | Live homepage text |
| PMD/NDMC Dam Reservoirs | **Reservoir** (5 named) | Live page navigation, confirmed by URL pattern per reservoir |
| PDMA Balochistan MHVRA | **District** (9 named) | Filenames individually read |
| IRSA Daily Data | **Unknown** — PDF content not opened this session | N/A |
| FFC DFSR / GLOF alerts | **Unknown** — PDF content not opened this session; "Nullah Lai" mentioned only in a homepage link title, not confirmed as the report's actual internal geographic unit | N/A |

**No source in this session was confirmed to report at tehsil, union-council, or village/mauza level.** Where a document's internal content was not opened, granularity is honestly recorded as unverified rather than inferred from the report family's title or the page it was linked from.

---

## Cyclone, GLOF, Landslide — first-pass research findings

| Hazard | What was found | Status |
|---|---|---|
| **Cyclone** | PMD's Tropical Cyclone Warning Centre confirmed real at `weather.gov.pk/tcwc` (mission/description page only — no advisory archive found this session, likely because no cyclone was active at time of check). SUPARCO DisasterWatch confirmed to carry a `cyclone` hazard layer/icon in its API. | PARTIALLY_VERIFIED (org confirmed; no historical advisory archive confirmed) |
| **GLOF** | Federal Flood Commission confirmed with **3 real, dated GLOF alerts** (see §F). SUPARCO DisasterWatch confirmed to carry a `glof` hazard layer/icon. | VERIFIED (via FFC) — the strongest of the three unresearched families |
| **Landslide** | SUPARCO DisasterWatch confirmed to carry a `landslide` hazard layer/icon (`Landslide_transparent.png`). **No dedicated PMD, NDMA, or PDMA landslide archive or page was found this session.** | PARTIALLY_VERIFIED (only via SUPARCO's hazard-layer icon; no direct landslide dataset/archive opened) |

None of these three families were force-fitted with an invented dataset where evidence was absent, per the task's explicit instruction.
