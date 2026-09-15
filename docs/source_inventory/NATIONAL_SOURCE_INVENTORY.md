# National Source Inventory — Pakistan Operational Risk Intelligence

**Phase 1 / Task 13 (ADR-0001).** This is a discovery/inventory document, not an ingestion task. No new scraper, DAG, table, or dependency was created. Every source below was either (a) directly navigated to and its page content read in this session, or (b) explicitly marked as discovered-but-unverified, per the research principles this task requires. Nothing is invented: where a URL, year, count, or format could not be confirmed, the field says `Unknown / Requires verification` rather than a guess.

**Companion machine-readable file:** [`source_inventory.csv`](source_inventory.csv) — 36 rows (30 primary-source datasets, 6 supporting-source candidates), validated by `tests/source_inventory/test_source_inventory.py`.

**Research date:** 2026-09-16, live browsing session against the real production websites listed below (not cached/historical snapshots).

---

## 1. How to read this document

- **Primary sources** (§2) are the six organizations the task named explicitly. Each dataset/material found on their sites is one row.
- **Supporting sources** (§3) are candidates discovered during research — named, given whatever evidence exists, and explicitly **not** integrated into any pipeline.
- **Priority** (P0–P4) reflects value to PORI's operational-risk purpose specifically, not general importance.
- **Historical classification** — `LIVE_CURRENT` (a live status/feed with no real archive), `RECENT_OPERATIONAL_HISTORY` (a dated archive covering recent seasons/years), `EVENT_HISTORY` (tied to a specific event or event-type category), `STATIC_REFERENCE` (a one-off or rarely-updated document).
- A **dataset/report family** (e.g. "PDMA Punjab Gauge Report") is distinguished from an **individual document** (e.g. one PDF) throughout — the inventory records families, with volume/depth noted per family.
- Where this session could not verify something by directly opening the page, the field is marked `Unknown / Requires verification` — never estimated.

---

## 2. Primary sources

### 2.1 NDMA — https://ndma.gov.pk

| Dataset | URL | Type | Depth (verified) | Priority | Classification |
|---|---|---|---|---|---|
| Monsoon Daily Situation Reports | `/sitreps?cat_id=3` | Situation report | Season-scoped: Report No.1 (26 Jun 2026) → No.82 (15 Sep 2026), confirmed by paging to first/last page | **P0** | RECENT_OPERATIONAL_HISTORY |
| Publications hub | `/publications` | Mixed | 8 categories, counts read directly off the site: Post Reports 3, CoE 1, NIDM Publications 16, Gender & Child Cell 6, MHVRA 8, Guidelines & Training Manuals 26, Newsletters 31, Annual Reports 3 | P2 | STATIC_REFERENCE |
| MHVRA district reports | `/publication_by_category/9` | Risk assessment | 8 district reports (Islamabad; Nowshera, KP; Rawalpindi, Bahawalpur, Jhang, Punjab; +3 more not individually opened) | **P1** | STATIC_REFERENCE |
| Guidelines & Training Manuals | `/publications` | Guideline/SOP | 26 items | P3 | STATIC_REFERENCE |
| Newsletters | `/publications` | Newsletter | 31 items, monthly cadence inferred from consecutive titles | P3 | STATIC_REFERENCE |
| Annual Reports | `/publications` | Annual report | 3 items, years not individually opened | P2 | STATIC_REFERENCE |

**Already used by this repo:** the Monsoon Daily Situation Reports archive is exactly what `scripts/extraction`/`scripts/parsing/parse_ndma.py` already targets.
**New finding:** the MHVRA district-report category — genuine sub-provincial hazard/vulnerability assessments, not currently referenced anywhere in the codebase.
**Not verified this session:** individual publication years/dates within each category; whether NDMA publishes anything below province granularity outside MHVRA.

### 2.2 PDMA Punjab — https://pdma.punjab.gov.pk

| Dataset | URL | Type | Depth (verified) | Priority | Classification |
|---|---|---|---|---|---|
| Daily Situation Reports | `/daily-situation-reports` | Situation report | 2 years listed: 2025, 2026 | **P0** | RECENT_OPERATIONAL_HISTORY |
| Gauge Report | `/gauge-reports` | River/gauge | 2 years listed: 2025, 2026; 15,274 rows already live in `pdma_gauge_readings` | **P0** | RECENT_OPERATIONAL_HISTORY |
| Rainfall Report | homepage ticker | Rainfall | Confirmed live via ticker link; 869 rows already live in `pdma_rainfall_readings` | **P0** | RECENT_OPERATIONAL_HISTORY |
| Earthquake Report | `/earthquake-reports` | Earthquake | 2 years listed: 2025, 2026 | P1 | EVENT_HISTORY |
| Weather Alert / Flood Alert / PEOC advisories | homepage ticker | Alert/advisory | Live ticker, English+Urdu mixed | P2 | LIVE_CURRENT |

**Already used by this repo:** Daily Situation Reports, Gauge Report, and Rainfall Report are exactly the three families the existing PDMA scraper targets.
**New finding, confirming a prior repo gap:** the Earthquake Report archive genuinely exists and is reachable at `/earthquake-reports` with a real 2025/2026 year listing — the architecture assessment previously found 3 downloaded earthquake PDFs with zero matching parser; this confirms the source page itself is real and scrapable, not a dead end.

### 2.3 PDMA Sindh — https://pdma.gos.pk

| Dataset | URL | Type | Depth (verified) | Priority | Classification |
|---|---|---|---|---|---|
| Monsoon 2026 Situation Reports | `/monsoon-2026-situation-reports/` | Situation report | **56 entries confirmed** ("Showing 1 to 10 of 56 entries") | **P1** | RECENT_OPERATIONAL_HISTORY |
| Monsoon 2025 Situation Reports | `/monsoon-2025-situation-reports/` | Situation report | Category link confirmed; entry count not opened | P1 | RECENT_OPERATIONAL_HISTORY |
| Heatwave Situation Reports (2025, 2026) | `/heatwave-situation-report-2026/` | Heatwave | 2 seasons confirmed by both year-links being present | P2 | EVENT_HISTORY |
| Rains 2026 Situation Reports | `/rains-2026-situation-reports/` | Rainfall/situation report | Category link confirmed present | P2 | EVENT_HISTORY |
| Cyclone-related news items (Thatta, Sujawal) | homepage news feed | Cyclone/evacuation | News posts only, not a structured archive; dated 2023–2024 | P3 | EVENT_HISTORY |

**Why this matters:** the platform currently has **zero** dedicated Sindh ingestion. This is the first session to confirm Sindh publishes a real, structured, dated, downloadable report archive (an HTML DataTable with a Download column per row) — materially more scrape-friendly than PDMA Punjab's plain year-grouped list.
**Genuinely new data family found:** a dedicated **heatwave** situation-report category — the first heatwave-specific source found anywhere in this inventory, notable because Sindh (Karachi) is Pakistan's principal heatwave-risk province.
**Not verified this session:** the internal geographic granularity of the PDF reports themselves (district-level content inside the documents was not opened).

### 2.4 PDMA Khyber Pakhtunkhwa — https://www.pdma.gov.pk

| Dataset | URL | Type | Depth (verified) | Priority | Classification |
|---|---|---|---|---|---|
| Daily Situation Reports (DSR), PEOC RMS | `https://rms.pdma.gov.pk/DSRs.aspx` | Situation report | **Twice-daily** (Morning/Evening shift rows), live through 15 Sep 2026 | **P0** | LIVE_CURRENT |
| Damages/Losses — Gender Wise Damages Report | `/damage-losses` | Damage, gender-disaggregated | Monthly reports Jan 2025–Jun 2026 (18 months) confirmed, plus 2024 partially visible, plus consolidated annual reports for 2024 and 2025 | **P1** | RECENT_OPERATIONAL_HISTORY |
| Monsoon Contingency Plans | homepage "Downloads & Publication" | Contingency plan | **15 consecutive annual plans, 2012–2026**, confirmed by title list | P2 | STATIC_REFERENCE |
| Winter Contingency Plans | homepage "Downloads & Publication" | Contingency plan | 7 consecutive winter-season plans, 2019-20–2025-26 | P3 | STATIC_REFERENCE |
| Heat Wave Plans | homepage "Downloads & Publication" | Heatwave contingency plan | 2 years: 2022, 2023 | P3 | STATIC_REFERENCE |
| Acts and Notifications | homepage "Downloads & Publication" | Legal/regulatory | ~15 items observed in a longer, uncounted list | P4 | STATIC_REFERENCE |

**Most significant finding in this entire inventory:** `rms.pdma.gov.pk` is a **separate application** (ASP.NET WebForms, distinct subdomain) from the main `pdma.gov.pk` CMS, publishing **twice-daily** situation reports — the highest frequency found at any provincial PDMA. KP currently has zero dedicated ingestion in this platform.
**Second significant finding:** the Gender Wise Damages Report is the only gender-disaggregated damage dataset found anywhere — a real dimension the platform's existing NDMA damage data does not have.
**Third finding:** the Monsoon Contingency Plan series is the deepest verified year-over-year static archive in this inventory (2012–2026, naming changed partway to "Summer Hazards Contingency Plan" — same document family, confirmed by reading the title list in order).
**Note on a homepage widget:** the "Today Peshawar Weather" widget on this page states `Source: Open-meteo` — i.e. a **third-party API**, not PMD directly. Recorded here so it is not mistaken for an official PMD feed.

### 2.5 PDMA Balochistan — https://pdma.gob.pk

| Dataset | URL | Type | Depth (verified) | Priority | Classification |
|---|---|---|---|---|---|
| MHVRA district reports | homepage "MHVRA Reports" block | Risk assessment | 6 districts confirmed by distinct filenames: Chaghai, Kachhi, Nushki, Sibi, Quetta, Gwadar; one filename dated 2021 | P2 | STATIC_REFERENCE |
| Daily Weather Reports & Advisory Alerts / Daily situation reports / Monthly Seismic reports | homepage section headings | Weather / situation / seismic | Section headings found via in-page search only; listings/archives not opened | P3 | LIVE_CURRENT (tentative — see notes below) |

**Confirms the architecture assessment's prior characterization:** this is genuinely the weakest primary site of the six — homepage text is nearly empty (`PDMA \| Provincial Disaster Management Authority \| Balochistan`), and its available documents are hosted on **Google Drive**, not the department's own domain — a real access-permanence risk worth recording rather than treating as equivalent to the other five sources.
**Not verified this session:** whether the Daily Weather Reports, Daily Situation Reports, and Monthly Seismic Reports sections lead to real, structured archives or are placeholder headings — this is explicitly left `Unknown / Requires verification` in the CSV rather than assumed live.

### 2.6 PMD — https://weather.gov.pk

| Dataset | URL | Type | Depth (verified) | Priority | Classification |
|---|---|---|---|---|---|
| Daily/3-Day/Weekly/Cities Forecast (NWFC) | homepage nav; served via NWFC | Weather forecast | Confirmed live; 108 rows already live in `pmd_daily_forecast` | **P0** | LIVE_CURRENT |
| Seasonal/Monthly Outlook | homepage ticker | Seasonal outlook | Titles observed on ticker only ("Monthly Outlook September 2026", "Seasonal Outlook SON 2026") | P2 | LIVE_CURRENT |
| **NDMC** — Bulletins, Dam Reservoirs, Satellite Indices, SPI Maps, Outlook Maps | `weather.gov.pk/ndmc` | **Drought** | Sub-navigation confirmed real via link discovery; individual pages not opened | **P1** | LIVE_CURRENT |
| **FFD** — Flood Bulletins & Advisories archive | `ffd.pmd.gov.pk/bulletins/archive` | Flood bulletin/advisory | **267 total records confirmed** ("Showing 1-30 of 267 record(s)"), spanning years 2024 and 2025 per the page's own year filter; live real-time river-data widget also present | **P0** | RECENT_OPERATIONAL_HISTORY |
| Radar, Ozone Watch | homepage nav | Imagery | Nav links confirmed; pages not opened | P4 | LIVE_CURRENT |
| Seismic, NAMC, R&D | homepage "Services" carousel | Seismic/agromet/research | Carousel labels only; no sub-page opened | P4 | LIVE_CURRENT |

**Strongest single finding in this entire inventory: FFD.** `ffd.pmd.gov.pk` is a distinct site (its own "Sign In", suggesting some restricted features) hosting a real 2-year, 267-record archive of daily flood bulletins and advisories, plus a live real-time river-data widget. This would directly complement the platform's existing numeric-only gauge data with actual forecast narrative text, for the exact same river network.
**Second finding: NDMC closes a complete gap.** The platform currently has no drought data anywhere — no table, no column, no field. NDMC's SPI (Standardized Precipitation Index) maps and drought bulletins are the only verified drought source in this inventory.
**Not verified this session:** exact format/frequency/granularity of NDMC's individual sub-pages, and of the Seasonal Outlook, Radar, Ozone Watch, Seismic, NAMC, and R&D services — all correctly left `Unknown / Requires verification`.

---

## 3. Supporting sources (discovered, not adopted)

Per the task's explicit instruction, none of these are integrated into any pipeline. Each entry states exactly what was verified and what was not.

| Organization | Official URL | Discovered material | Relevance | Likely data type | Adopt now/later/not yet | Verification notes |
|---|---|---|---|---|---|---|
| **Flood Forecasting Division (FFD)** | `ffd.pmd.gov.pk` | See §2.6 — full record is under PMD, not duplicated here | High | Flood bulletins/advisories | **Now** (already P0 above) | Fully verified this session; listed here only because the task named FFD as a supporting-source candidate to discover. |
| **WAPDA** | `wapda.gov.pk` | Corporate homepage: news, dam construction status ("Under Construction / Future Construction / Operational"), tenders | Low-medium | Corporate/news | Not yet | Homepage text searched for "reservoir" — zero matches. No live hydrology data table found on the homepage in this session; a dedicated data section may exist elsewhere but was not located. |
| **IRSA** (Indus River System Authority) | `pakirsa.gov.pk` | "Daily Data" / "Daily Water Situation" nav page; "Telemetry Sites Locations" item seen in Latest Updates | High | Reservoir/river flow (Tarbela, Mangla, Chashma) | Later | Navigated to `DailyData.aspx` and confirmed the page title ("Daily Water Situation") and site structure are real; the actual data table content was **not extracted** this session. Do not assume format/frequency until a follow-up session opens the real table. |
| **Federal Flood Commission** | *Not verified* | Named as a cross-link on IRSA's homepage ("Links With Ministries") | Unknown | Unknown | Not yet | Deliberately given no URL — its own site was never visited this session; recorded only because it was named by another verified source. |
| **SUPARCO** | `suparco.gov.pk` (DisasterWatch reportedly at `disasterwatch.sgs-suparco.gov.pk`) | Web-GIS portal for satellite-based flood/hazard mapping | Potentially high | Satellite flood-extent/hazard mapping | Later | **This record's URL came from a web search result, not direct navigation** — the portal itself was not opened in this session. Flagged explicitly so it is not mistaken for a verified page visit like every other primary-source entry in this document. |
| **EPA Punjab** (Environment Protection Department) | `epd.punjab.gov.pk` | An "AQI Forecasting and Advisories System" referenced in a department PDF found via web search | Medium | Air Quality Index (AQI) | Later | Homepage was directly visited and confirmed real/live, but returned almost no extractable text (JS-heavy site) in this session. The AQI system itself is known only from a PDF found via web search, not from a directly-browsed live AQI page — do not claim a working AQI feed exists until one is actually opened. |

---

## 4. Priority summary (from `source_inventory.csv`, verified by count, not estimated)

| Priority | Meaning | Count |
|---|---|---:|
| P0 | Must Have | 8 |
| P1 | Highly Valuable | 7 |
| P2 | Useful | 9 |
| P3 | Reference | 7 |
| P4 | Ignore | 5 |
| **Total** | | **36** |

## 5. Historical classification summary

| Classification | Count |
|---|---:|
| STATIC_REFERENCE | 10 |
| RECENT_OPERATIONAL_HISTORY | 8 |
| LIVE_CURRENT | 8 |
| EVENT_HISTORY | 4 |
| Unknown / Requires verification (supporting sources only) | 6 |
| **Total** | **36** |

## 6. Record-type summary

30 primary-source dataset records (across NDMA, PDMA Punjab, PDMA Sindh, PDMA KP, PDMA Balochistan, PMD) + 6 supporting-source candidate records = **36 total rows**.

---

## 7. What still requires deeper verification before any integration decision

Recorded here explicitly, rather than silently left for someone to rediscover later:

1. **IRSA's actual Daily Data table** — page confirmed real, content not opened. This is the single most valuable next verification step (P1), since it would directly complement the platform's existing gauge data with authoritative reservoir figures for Tarbela/Mangla/Chashma.
2. **NDMC's five sub-pages** (Bulletins, Dam Reservoirs, Satellite Indices, SPI Maps, Outlook Maps) — confirmed to exist via link discovery only; format, frequency, and geographic granularity all unverified. This is the platform's only lead on drought data.
3. **PDMA Balochistan's three homepage-listed sections** (Daily Weather Reports & Advisory Alerts, Daily situation reports, Monthly Seismic reports) — headings found, archives not opened; unclear whether they lead anywhere real.
4. **SUPARCO's DisasterWatch portal** — URL sourced from a web search, not a direct visit; needs an actual browsing session before it can be trusted as a source at all.
5. **EPA Punjab's live AQI page** — department site confirmed live; the actual AQI dashboard/API was not located under this domain in the time available.
6. **Federal Flood Commission** — name only, no URL verified.
7. **Cyclone and GLOF (Glacial Lake Outburst Flood) data families** — neither was confirmed to have a dedicated official source in this session. Sindh's cyclone-related content found was unstructured news, not a report family. GLOF was not investigated at all this session despite being explicitly named in the task's data-family list — flagged honestly as **not researched**, not as "doesn't exist."
8. **Landslide-specific data** — not investigated this session; also flagged as not researched.
9. **PMD's Radar, Ozone Watch, Seismic, NAMC, and R&D services** — nav links confirmed, no sub-page opened.
10. **Exact in-document geographic granularity** for several PDF-based report families (PDMA Sindh situation reports, PDMA Punjab daily situation reports, PDMA KP DSRs) — the report *pages* were confirmed, but the *content inside* individual PDFs was not opened, so district/tehsil-level detail inside those documents is unverified.

## 8. Explicit non-claims

- No API was found and verified anywhere in this session except the third-party Open-Meteo widget embedded in PDMA KP's homepage (explicitly not a PMD/government API).
- No source in this inventory was confirmed to expose machine-readable (JSON/CSV) data directly — every verified source is either an HTML page with PDF links, or an HTML/JS table (PDMA Sindh's DataTable, PDMA KP's RMS grid) whose underlying documents are still PDF or unconfirmed format.
- No licensing or redistribution terms were found stated on any of the six primary sites in this session; this remains an open question for Phase 12 (per the architecture assessment's own D.4 unknown #11) and is not resolved by this task.
- No historical depth beyond what is explicitly stated above is claimed for any source — the presence of a navigation menu or "Archive" label was never treated as proof of deep history without paging to confirm it, per the task's research principles.
