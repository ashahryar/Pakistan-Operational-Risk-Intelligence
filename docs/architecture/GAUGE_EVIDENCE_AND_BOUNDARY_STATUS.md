# Gauge evidence registry and administrative boundary foundation — status (Task 25)

Two deliverables: (A) a structured station evidence registry with a time-boxed official-source investigation; (B) a reusable administrative boundary + point-in-polygon + crosswalk foundation. **Result: 0 stations are eligible for administrative risk.** No authoritative station evidence could be obtained, so eligibility stays strict. The boundary foundation is ready for the day authoritative coordinates exist.

## A. Official station evidence

Registry: `config/gauge_station_evidence.yaml` (`gauge-geo-2.0.0`, fields: station_name, source, source_type, source_url, source_record, station_id, latitude, longitude, district, tehsil, river, basin, evidence_status, evidence_strength, notes, retrieved). Output: `data/analytics/geo/gauge_station_evidence.json`. Evidence statuses: `authoritative`, `official_secondary`, `secondary`, `conflicting`, `unresolved`. Only an official owner explicitly stating a district or coordinates is `authoritative`; a government-looking website is not enough.

Investigated (all recorded in the registry's `investigation_log`; none produced authoritative evidence):

| Source | What happened |
|---|---|
| IRSA (pakirsa.gov.pk) | not reachable from the build environment; no telemetry site list found elsewhere |
| FFC flood-fighting-plan index | reachable; lists NDMA / Punjab zone-wise / PDMA KP plans and a Mangla manual; no station locations |
| FFC per-headworks plans (docx) | URLs returned 404; one download was unreadable (OS denied read access) — not used |
| FFC/WAPDA Mangla reservoir manual (PDF) | 2-page scan, no text layer, no OCR available — content unverified, not used |
| WAPDA Tarbela page | 404 |
| Punjab Irrigation Department | only secondary references retrieved |

Secondary evidence recorded (never eligible): Marala→Sialkot, Khanki→Gujranwala, Trimmu→Jhang, Balloki→Kasur (`resolved_inferred`); Panjnad→Muzaffargarh (stays `unresolved`: Muzaffargarh is not in `geo.admin_unit`); Tarbela (Swabi vs Haripur) and Rasul (Jhelum vs Mandi Bahauddin) conflict → `ambiguous`; Mangla `caveated`. No coordinates exist for any station: the PDMA feed has none and no authoritative source was found. **No coordinate or station id was invented.**

## B. Boundary foundation

Dataset: **Pakistan – Subnational Administrative Boundaries (COD-AB)**, published by OCHA FISS on HDX (original source WFP SDI), v01, valid_on 2022-09-09, HDX record modified 2026-08-14, **CC BY-IGO**, levels country / province / district (also admin3, not used). Stored under gitignored `data/raw/boundaries/hdx_cod_ab_pak/` (archive sha256 in `config/admin_boundary_sources.yaml`; re-downloadable). It is a third-party humanitarian compilation, **not government-certified**; vintage 2022 (newer districts such as Kot Addu, Murree, Taunsa are absent). Provenance and limitations are in `config/admin_boundary_sources.yaml`.

Structural validation (`pipeline/geo/boundaries.py`, real data): CRS84 accepted (other CRS are rejected, no reprojection); 7 provinces, 160 districts; 0 duplicate names, 0 missing ids, 0 invalid rings, 0 units outside the Pakistan extent, 0 orphan districts; 3 multipart provinces, 8 multipart districts; interior-point overlap sample test passed for all 160 districts. **Not checked:** full topology (self-intersections) — no geometry library is installed.

Crosswalk (`gauge_boundary_crosswalk.json`, deterministic, no fuzzy matching): provinces 4 exact + 3 alias (Azad Kashmir, Gilgit Baltistan, Islamabad); districts 54 exact + 2 alias (`D. I. Khan`, `Leiah`→Layyah) + **104 unmatched**. The canonical geography (`geo.admin_unit`, 69 districts) covers only a third of the boundary districts, so most boundary units stay visible as `unmatched` rather than being force-mapped. 13 PORI districts have no boundary polygon (Mangla, Kamra, Fort Munro, Joharabad and others, plus 9 that are absent from the 2022 file or merged). Matches are `pending_manual_review`.

Point-in-polygon (`locate_station`): coordinate → district polygon → canonical unit, always labelled `coordinate_based`. Points on a boundary or outside all polygons are never assigned; overlapping polygons report `multiple`. Verified on the real file (Lahore centre → Lahore; (0,0) and London → outside) and on synthetic geometry.

## Eligibility policy (config, `config/admin_boundary_sources.yaml: policy`)

Eligible: `authoritative` evidence only — either an explicit official district statement, or authoritative coordinates that land inside exactly one district whose boundary unit has an exact/alias crosswalk to a non-caveated PORI unit (the HDX dataset is explicitly marked `accepted_for_coordinate_mapping`). Never eligible: secondary, official_secondary (policy flag, default off), vague "near X", river/basin inference, fuzzy names, conflicting evidence, caveated stations, invalid/reversed coordinates.

## Real-data result (41 stations, 3,686 observations)

| | Task 24 | Task 25 |
|---|---:|---:|
| resolved_authoritative / resolved_coordinate | 0 | 0 |
| resolved_inferred (secondary) | 4 | 4 |
| ambiguous (Tarbela; Rasul added) | 1 | 2 |
| caveated (Mangla) | 1 | 1 |
| unresolved (Panjnad's evidence names a unit absent from canonical geography) | 35 | 34 |
| eligible stations | 0 | 0 |
| observations eligible for risk | 0 | 0 |
| observations unresolved | 3,686 | 3,686 |

(Exact per-status counts are in `data/analytics/geo/gauge_geography_coverage.json`.)

## Remaining gap

An official station list with district or coordinates (IRSA telemetry sites, FFC/Punjab Irrigation per-headworks documents) is still needed; the registry and boundary pipeline accept it without code changes: add `authoritative` records with `latitude`/`longitude` (or `district`) and re-run `scripts/geo/run_gauge_geography.py`. Separately, `geo.admin_unit` should be extended from the boundary dataset (a PostGIS/DB task) so that 104 unmatched districts can be matched.
