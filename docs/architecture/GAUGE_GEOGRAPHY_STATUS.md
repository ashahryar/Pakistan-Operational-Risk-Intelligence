# Gauge geography and hydrographic context — status (Task 24)

> Superseded in part by Task 25 (`GAUGE_EVIDENCE_AND_BOUNDARY_STATUS.md`): the evidence registry schema, eligibility policy (now in config) and boundary/crosswalk foundation changed; the Task 24 results below are the historical baseline.

A repository-managed, evidence-tiered mapping layer between PDMA gauge stations and canonical geography. **It does not make the gauge data geographically usable yet: after Task 24, 0 of 41 stations are eligible for administrative risk. That is the honest result of the evidence available, not a defect.**

## What exists

| Artifact | Purpose |
|---|---|
| `pipeline/geo/gauge_station.py` | station inventory built from the real Gold gauge rows (one record per distinct station) |
| `pipeline/geo/hydrography.py` | river / hill-torrent-group context, kept separate from administrative geography |
| `pipeline/geo/gauge_mapping.py` | evidence → mapping status, eligibility policy, application to gauge rows, before/after coverage |
| `config/gauge_station_evidence.yaml` | versioned evidence (`gauge-geo-1.0.0`, 2026-10-02, `pending_manual_review`) |
| `scripts/geo/run_gauge_geography.py` | runs it on real data, validates, writes `data/analytics/geo/gauge_{station_inventory,station_mapping,geography_coverage}.json` |

No PostgreSQL table was created: a versioned repository artifact is sufficient at this stage, and `geo.admin_unit` / `geo.name_alias` are untouched (one read-only `geo.admin_unit` lookup for ids).

## Evidence found (and not found)

- The PDMA gauge feed publishes only station name, river heading, level, danger level, discharge and flow status. **No coordinates, station ids, district, basin or catchment.**
- No authoritative boundary dataset exists in the project, so **no coordinate / point-in-polygon mapping is possible and none was made** (0 coordinate-based mappings). No station coordinates were invented.
- No official (WAPDA / FFD / IRSA / PMD / irrigation department) document giving station → district was located. The project's source inventory records IRSA/FFC reservoir pages but not station locations.
- Web search returned only secondary references (encyclopedia / news), with per-result attribution unverified, and they conflict for Tarbela (Swabi vs Haripur). They are recorded as evidence of class `secondary`, which can produce **at most `resolved_inferred`, never eligible**.

## Mapping hierarchy and eligibility

`resolved_authoritative` → `resolved_coordinate` → `resolved_source_reported` are **eligible** (`eligible_for_admin_risk = true`), and only when the canonical unit exists and is not caveated. `resolved_inferred`, `ambiguous`, `caveated` and `unresolved` are never eligible. Name similarity alone never maps a station. Each mapping carries version, date, source, source record, basis, confidence, caveat and `validation_status = pending_manual_review` (no reviewer is claimed).

## Real-data result (41 stations, 3686 observations, 93 dates)

| Status | Stations |
|---|---:|
| resolved_authoritative / resolved_coordinate / resolved_source_reported | 0 |
| resolved_inferred (Marala→Sialkot, Khanki→Gujranwala, Trimmu→Jhang, Balloki→Kasur; secondary, ineligible) | 4 |
| ambiguous (Tarbela: Swabi vs Haripur) | 1 |
| caveated (Mangla) | 1 |
| unresolved | 35 |
| **eligible for risk** | **0** |

| Metric | Before (Task 23) | After | Change |
|---|---:|---:|---:|
| stations with candidate admin geography | 1 | 5 | +4 |
| stations eligible for admin risk | 0 | 0 | 0 |
| observations with candidate admin geography | 93 | 465 | +372 |
| observations attributable for risk | 0 | 0 | 0 |
| observations unresolved for risk | 3686 | 3686 | 0 |
| stations with river context (source-reported) | 40 | 40 | 0 |
| stations with basin context | 0 | 0 | 0 |

"Before" counts Mangla as having geography but caveated (Task 23 never let it drive a status), so the effective risk coverage before and after is the same: none. Adding candidate geography did not raise it, and is not claimed to.

Top unresolved stations by observations: every station has 93 daily observations (Bhimber 58); there is no single high-volume station to prioritise. Chashma, Kalabagh, Taunsa, Tarbela, Marala and the other Indus/Chenab/Jhelum/Ravi/Sutlej stations are all in the unresolved-for-risk set.

## Hydrographic context

River/group headings are carried as printed by PDMA (`source_reported`): 40 stations; 5 main rivers (Indus, Jhelum, Chenab, Ravi, Sutlej), the rest are headings for torrent/nullah groups (`NULLAHS`, `RAJANPUR/DG KHAN HILL TORRENTS`), flagged `torrent_or_nullah_group` rather than rivers. One station (`Lai FD and DEO`, heading `NULLAHS DATA SOURCE: F`) has a parsing artefact as heading and is left unresolved. Basin and catchment are null for all stations (not published by the source; no basin hierarchy invented). A river or basin is never converted into a district.

## Mangla

Task 23 resolved Mangla by name to the Task 10 seed row "Mangla", which that seed itself flags as *not a real district* (a reservoir/dam town in Mirpur, AJK). Final status: **`caveated`, not eligible; caveat retained**. A secondary reference places it in Mirpur (which exists in `geo.admin_unit`), but secondary evidence is not adopted. Its primary representation is hydrographic (River Jhelum). Correcting it requires an official source.

## Risk engine integration

`scripts/risk/run_risk_engine.py` now decides gauge geography **only** from eligible mappings (the legacy Gold resolution is no longer trusted on its own); everything else stays in `unresolved_signals.jsonl` with `geography_unresolved_reason`. The engine, thresholds and weights are unchanged. Effect on the real run: gauge resolved 93 → 0 observations; unresolved signal records 3629 → 3722; risk rows 1677 → 1586 (the 91 removed rows existed only because of the caveated Mangla signal and were all `INSUFFICIENT_DATA`); no other status changed.

## Assumptions and limitations

Station geography is treated as static (no relocation evidence; no effective dates invented). Coverage cannot improve without an official station list with district or coordinates, plus a boundary dataset. The sibling station `Lai FD and DEO` is not merged with `Lai` (no evidence they are one station). Admin ids need a reachable `geo.admin_unit`; without it mappings degrade to ineligible.
