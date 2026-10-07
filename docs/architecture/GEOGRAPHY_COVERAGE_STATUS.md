# Authoritative geography and data coverage — evidence audit (Task 37)

**Result: no gauge station could be mapped to an administrative unit from authoritative evidence, so gauge geography stays unresolved. One crosswalk relationship was improved with real official evidence (Nawabshah). No scoring change: `score_v2` stays disabled, `risk_score` stays NULL, and the number of newly eligible observations is 0.**

Machine-readable: `data/analytics/geo/coverage_evidence_audit.json` (`python scripts/geo/audit_coverage_task37.py`, deterministic, no database writes). Evidence registry: `config/crosswalk_evidence.yaml`.

## Which signals can be tied to which administrative units, and on what evidence

| Domain | Rows | Resolved | Admin units with a series | Dates (span, missing within span) | Geography method | Status |
|---|---:|---:|---:|---|---|---|
| rainfall (PDMA) | 869 | 76 % | 42 | 2025-03-03 → 2026-07-14 (78 dates, 421 missing) | Task 10 deterministic name resolver | qualified: official source, project-resolved names |
| weather (PMD) | 39 | 69 % | 27 | 1 date | Task 10 city resolver | one date: no history |
| gauge (PDMA/FFD) | 3,686 | **0 %** | **0** | 93 dates | none — no authoritative evidence | unresolved |
| air quality (EPA Punjab) | 352 | 100 % | 1 (Lahore) | 351 dates, 0 missing | single named city | continuous, one geography |
| hazard alert | 38 | 95 % | – | 5 dates | region resolver | contextual only |
| disaster event | 1,543 | 100 % | – | 80 dates | province names | contextual only |

Nothing in the table is "government-certified". The canonical model (`geo.admin_unit`, 69 districts) is a locally consolidated list and the HDX COD-AB boundary file is a third-party humanitarian compilation (vintage 2022-09-09).

## Gauge stations (41 stations, 3,686 observations)

Re-audited against the project's own sources and a time-boxed official-source search.

* **PDMA gauge sitreps** (410 PDFs in 2026): list river, site, design capacity, flood limits and flows. No district, no coordinates.
* **FFC daily flood reports** (5 PDFs read as text): no sentence pairs a station with a district; district names occur only in weather-forecast region lists.
* **Official sites** (FFC annual report, per-headworks plans): ffc.gov.pk refused the connection, as in Task 25. A web search restricted to official domains returned titles only. Nothing was verified, so nothing was used.

| State | Stations | Detail |
|---|---:|---|
| authoritative / eligible | 0 | none added |
| secondary-only (not eligible) | 4 | Marala → Sialkot, Khanki → Gujranwala, Trimmu → Jhang, Balloki → Kasur |
| CONFLICTING (ambiguous in the mapping) | 2 | Tarbela (Swabi / Haripur), Rasul (Jhelum / Mandi Bahauddin); every source kept, no vote |
| caveated | 1 | Mangla (seed row is not a real district) |
| unresolved | 34 | including Panjnad, whose only evidence names a unit absent from the canonical model |

The existing statuses (`ambiguous`, `resolved_inferred`, …) are not renamed; the Task 37 report presents `ambiguous` records as `conflict_status: CONFLICTING`.

## Administrative crosswalk

* Provinces: 4 exact, 3 alias (unchanged). Districts: **54 exact, 3 alias, 103 unmatched** (was 54 / 2 / 104).
* **Added: PK719 "Shaheed Benazir Abad" → canonical "Nawabshah" (id 59), ALIAS.** Evidence: Provincial Assembly of Sindh, Sindh Act No. XIV of 2023 (notification 8 June 2023), which says "District Shaheed Benazirabad (Nawabshah)"; I read it from the downloaded PDF text, not from a search summary. The boundary spelling differs from the Act's by a space; the bridge is declared, not fuzzy. This is a name equivalence, not a boundary certification, and it stays `pending_manual_review`.
* Not applied: Karachi (one canonical unit against six boundary districts → CONFLICTING); Kot Addu, Murree and Wazirabad (absent from the 2022 file); towns/tehsils seeded as districts (Fort Munro, Joharabad, Kamra, Mangla, Khanpur, Noorpur Thal, Rawalakot, Turbat — containment is not identity); 103 boundary districts the canonical model does not contain (extending `geo.admin_unit` would redefine the canonical model and is a separate DB task).
* Canonical ids are unchanged (a test checks every previously matched id).
* Evaluated and not applied (UNVERIFIED): rainfall station names `Jehlum`, `MB Din`, `TT Singh`, `Layyah (Karor)`, `Sargodha (City)`, `Sargodha City`, `Sialkot (City)`. A simulation resolving all 31 rows would add 5 eligible rainfall observations and no two-group cell, and no source states the equivalences.

## Newly eligible observations: 0

Before and after eligibility counts are identical in every domain (rainfall 46 eligible, air quality 320, others 0). Crosswalk improvement affects only coordinate-derived mapping, and no station has coordinates.

## Ranked gaps (transparent ordinal sum; raw row count is not an input)

1. **Authoritative gauge station geography** (score 17.7): 41 stations and 3,686 observations on a continuous series, but no retrievable official list.
2. Dated weather history accumulation (14.0): 27 resolved geographies, needs ≥ 31 dated daily collections; DAGs are paused and PMD overwrites `latest.json`.
3. A second continuous air-quality geography (13.3): needs a new source.
4. Rainfall station-name aliases (9.2): +5 observations, no evidence.

**Recommended next evidence gap:** obtain an official station list (FFD / WAPDA / IRSA / Punjab Irrigation per-headworks documents) by manual retrieval. Add the records as `authoritative` entries in `config/gauge_station_evidence.yaml`; the Task 24/25 pipeline accepts them without code changes.

## What did not change

No serving contract, dashboard, DAG, database or AWS change was needed. Scoring remains `enabled: false` with `weights: {}`; the Task 36 contract still abstains even when signals are eligible (a test covers it).

## Limitations

The gap scores are ordinal judgements about measured quantities, not an estimate of value. The crosswalk evidence for the two older aliases (`D. I. Khan`, `Leiah`) is not recorded. Official-site retrieval was limited by network access from this environment, so the absence of evidence here is not proof that official documents do not exist.
