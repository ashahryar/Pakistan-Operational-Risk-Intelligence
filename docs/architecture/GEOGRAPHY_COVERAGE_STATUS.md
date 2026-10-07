# Authoritative geography and data coverage — evidence audit (Tasks 37 and 38)

**Result after Task 38 (partial evidence): 2 of 41 gauge stations now have an eligible, evidence-backed administrative mapping — Chashma → Mianwali and Trimmu → Jhang — covering 186 of 3,686 gauge observations, of which 126 satisfy the scoring data contract. The other 39 stations remain unresolved, conflicting, secondary-only or caveated. `score_v2` stays disabled, `risk_score` stays NULL, and no new cell has two independent signal groups.**

Machine-readable: `data/analytics/geo/coverage_evidence_audit.json` (`python scripts/geo/audit_coverage_task37.py`, deterministic, no database writes). Evidence registries: `config/gauge_station_evidence.yaml` (gauge stations), `config/crosswalk_evidence.yaml` (crosswalk).

## Which signals can be tied to which administrative units, and on what evidence

| Domain | Rows | Resolved | Admin units with a series | Dates (span, missing within span) | Geography method | Status |
|---|---:|---:|---:|---|---|---|
| rainfall (PDMA) | 869 | 76 % | 42 | 2025-03-03 → 2026-07-14 (78 dates, 421 missing) | Task 10 deterministic name resolver | qualified: official source, project-resolved names |
| weather (PMD) | 39 | 69 % | 27 | 1 date | Task 10 city resolver | one date: no history |
| gauge (PDMA/FFD) | 3,686 | **5.05 %** (186) | **2** | 93 dates, 0 missing | official owner evidence for 2 stations only | 39 of 41 stations unresolved |
| air quality (EPA Punjab) | 352 | 100 % | 1 (Lahore) | 351 dates, 0 missing | single named city | continuous, one geography |
| hazard alert | 38 | 95 % | – | 5 dates | region resolver | contextual only |
| disaster event | 1,543 | 100 % | – | 80 dates | province names | contextual only |

Nothing is "government-certified". The canonical model (`geo.admin_unit`, 69 districts) is a locally consolidated list; the HDX COD-AB boundary file is a third-party humanitarian compilation (vintage 2022-09-09).

## Gauge stations (41 stations, 3,686 observations, 93 daily dates each; derived from the repository)

### Sources retrieved in Task 38 (2026-10-07)

| Source | What it states | Use |
|---|---|---|
| WAPDA, "Chashma Hydel Power" page (html sha256 `688960af…`) | "The barrage is located on the Indus River near the village of Chashma in Mianwali District" | **applied**: Chashma → Mianwali |
| WAPDA, "Tarbela 5th Extension" page (`f74c666c…`) | "Tarbela Dam is located on on Indus River, District Swabi, Khyber Pakhtunkhwa." | recorded, **not applicable**: Swabi is not in `geo.admin_unit` |
| WAPDA, "Mangla Dam" page (`cabf002d…`) | "about 30 km upstream of Jhelum city" — no district | nothing to apply; Mangla stays caveated |
| Punjab Irrigation Department (FRAU), *Flood Report 2025* (143 pp., sha256 `ed8fdd54…`), Table 4 "Breaching Sites Location", printed p. 99 | latitude/longitude for 10 headworks (+ Shahdara, Jinnah Barrage) **of the breaching section**, with its chainage | applied only through a stability test (below) → Trimmu |
| Punjab Irrigation Department (FRAU), *Flood Atlas 2022* (34 pp.) | flood limits and narrative; "gauge at Jassar Bridge in Shakargarh", "Shahdara Railway Bridge near Lahore" | place/proximity wording, no district statement: not used |
| FFD (ffd.pmd.gov.pk) pages | reservoir levels, no station table | nothing usable |
| FFC (HTTP 500), IRSA (connection refused) | – | unreachable; limitation recorded |

PDF contents were read from the downloaded files (text layer; the coordinate table digits were also checked against a rendered page image), not from search summaries.

### How coordinates are used (the one code change)

The only official coordinates found belong to **breaching sections**, whose chainage (RD along a bund) is stated in the same row — up to about 6 km from the structure — and headworks sit on rivers that form district boundaries. So a bare point-in-polygon result would be unreliable (a point in the Khanki row falls in Gujrat; Sulemanki's falls in Okara). `pipeline/geo/boundaries.py::locate_within_radius` and an optional `position_uncertainty_m` on an evidence record express this: the centre and 64 probe points out to the stated uncertainty must all fall inside the **same single boundary district**, otherwise no district is attributed and the evidence is only preserved. The radius per station is the chainage converted to metres (RD in feet × 0.3048; a bare "RD n" read as n thousand feet, the larger value) rounded up to 500 m. Evidence without the field behaves exactly as before.

| Station | Official coordinate result | Outcome |
|---|---|---|
| Trimmu | Jhang at every probe up to 5.5 km (still Jhang at 12 km; only an 18 km disc leaves it) | **eligible**, `resolved_coordinate`, `coordinate_based`, medium confidence |
| Rasul, Marala, Khanki, Qadirabad, Panjnad, Sidhnai, Islam | disc spans 2–3 districts | refused, evidence kept |
| Suleimanki | disc leaves every polygon | refused |
| Balloki | stable, but in Nankana Sahib, which has no canonical unit and contradicts the secondary Kasur candidate | not applied |
| Shahdara | breaching section is on a distributary, no bound on the offset | deferred (`deferred_official_coordinates`) |
| Kalabagh | the table lists Jinnah Barrage; the report does not say the PDMA "Kalabagh" gauge is that barrage | deferred |

Identity assumption: a PDMA station name equals the same-named site on the same river (the design capacity also matches for Marala, Qadirabad, Trimmu, Rasul, Suleimanki, and for Chashma by name and river). This is the part of the Trimmu and Chashma mappings that a reviewer should confirm.

### Station states

| State | Stations |
|---|---|
| eligible (authoritative) | **2**: Chashma (owner district statement, derivation `source_reported`), Trimmu (official coordinates, `coordinate_based`) |
| CONFLICTING (`ambiguous`) | 2: Tarbela (authoritative Swabi, secondary Haripur — and Swabi is not canonical), Rasul (Jhelum / Mandi Bahauddin; official coordinates unstable) |
| secondary-only (ineligible) | 3: Marala → Sialkot, Khanki → Gujranwala, Balloki → Kasur |
| caveated | 1: Mangla |
| unresolved | 33 (the 20+ hill-torrent and nullah sites have no evidence at all; the rest are listed above) |

Trimmu was a secondary-only candidate (Jhang) in Task 37; the same district now rests on official coordinates, not on the secondary record. Panjnad's evidence names Muzaffargarh, which is not in `geo.admin_unit`.

### Coverage impact

| | Before (Task 37) | After (Task 38) |
|---|---:|---:|
| stations with an eligible mapping | 0 | 2 |
| gauge observations attributable to an admin unit | 0 | 186 |
| gauge observations eligible under the scoring contract (≥ 30 prior observations) | 0 | **126** (2 × (93 − 30)) |
| gauge observations with too little history | 0 | 60 |
| admin units with an eligible gauge series | 0 | 2 (Mianwali, Jhang) |
| cells with ≥ 1 eligible signal group | 358 | 484 |
| cells with 2 independent groups | 8 | 8 |

Neither Mianwali nor Jhang has an eligible signal from another independence group, so no cell gains a second group. Task 39 then regenerated the risk output so production matches the audit: `risk.operational_risk` went from 1,586 to 1,771 rows (185 new Mianwali/Jhang rows, none removed, `risk_score` still NULL on every row).

## Administrative crosswalk (unchanged in Task 38)

Districts: 54 exact, 3 alias, 103 unmatched. The only Task 37 addition is PK719 "Shaheed Benazir Abad" → Nawabshah (id 59), from Sindh Act XIV of 2023 ("District Shaheed Benazirabad (Nawabshah)"). Karachi (one canonical unit, six boundary districts) is CONFLICTING and not applied; Kot Addu, Murree and Wazirabad are absent from the 2022 file; towns/tehsils seeded as districts stay unmatched; 103 boundary districts (e.g. Swabi, Haripur, Awaran) have no canonical unit. Canonical ids are unchanged. Seven rainfall station-name candidates (`Jehlum`, `MB Din`, `TT Singh`, …) stay UNVERIFIED (simulation: +5 eligible observations, no new two-group cell).

## Ranked gaps (transparent ordinal sum; raw row count is not an input)

1. **Official gauge-site coordinates or district statements** (18.7): the 9 stations whose breaching-section coordinates were unstable plus Tarbela; FFD / IRSA / FFC per-headworks documents were unreachable.
2. Canonical model extension for authoritative districts (14.0): Swabi for Tarbela — requires an approved change to `geo.admin_unit`; not done.
3. Dated weather history accumulation (14.0).
4. A second continuous air-quality geography (13.3).
5. Rainfall station-name aliases (9.2).

**Recommended next evidence gap:** official gauge-**site** coordinates or district statements (for example the FFD telemetry station list or the FFC per-headworks flood-fighting plans). Add them as `authoritative` records to `config/gauge_station_evidence.yaml`; no code change is needed.

## Limitations

* The two mappings rest on name identity between the PDMA station and the owner's site, and (Trimmu) on a third-party boundary file plus an offset bound derived from a chainage in the source; both are marked `pending_manual_review`.
* The 126 eligible observations are signals that satisfy the data contract, not a score; there are still no evidence-based weights or outcome labels.
* The gap scores are ordinal judgements about measured quantities. Two official sites were unreachable from this environment, so absence of evidence there is not proof it does not exist.
