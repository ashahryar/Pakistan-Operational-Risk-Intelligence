# Geographic serving layer — status (Task 26)

Boundary geometry, the Task 25 crosswalk and the Task 23 operational-risk output are now served from PostgreSQL through read-only FastAPI endpoints.

```
geo.admin_unit (canonical, untouched)  +  COD-AB boundaries (separate layer)  +  Gold operational risk
        -> geo.boundary_* / risk.operational_risk -> views -> FastAPI (/api/v1/...)
```

## PostGIS: not available — what was done instead

`postgres:15` (15.19) in the project's Docker Compose has **no PostGIS** (`pg_available_extensions` has no `postgis`; installed extensions: `plpgsql` only). Swapping the database image would be new infrastructure, so it was not done. Consequences, stated plainly:

- **Geometry is stored as validated GeoJSON `jsonb`** (CRS84), not native PostGIS geometry, and there is **no spatial index** and no server-side spatial query. Point-in-polygon remains the pure-Python utility from Task 25 (`pipeline/geo/boundaries.py`).
- `db/migrations/0026b_postgis_geometry.up.sql` is written and structure-tested but **not executed against any PostGIS server**. On this server it is a guarded no-op (verified on the scratch copy: no column added, nothing half-applied). On a PostGIS server it adds `geom geometry(MultiPolygon, 4326)`, populates it from the GeoJSON, creates a GiST index and records `ST_IsValid` (it never repairs geometry).

## What was created (migration `db/migrations/0026_geo_serving_layer.{up,down}.sql`, additive + reversible)

| Object | Purpose |
|---|---|
| `geo.boundary_source` | dataset, publisher, version, valid_on, license, URL, retrieved date, sha256, CRS, validation report |
| `geo.boundary_admin_unit` | feature id, name, level, parent, GeoJSON geometry, validity + notes, original properties |
| `geo.boundary_crosswalk` | boundary → canonical unit, status (exact/alias/manual_verified/ambiguous/unmatched), basis, confidence, source |
| `risk.operational_risk` | serving copy of the Task 23 rows (`risk_score` NULL; `is_current` flag instead of deletes) |
| `risk.latest_operational_risk` (view) | each unit's own maximum risk date — no reference to today's date |
| `geo.current_boundary` (view) | one matched, valid boundary per canonical unit (latest source version wins) |
| `geo.operational_risk_map` (view) | every canonical province/district + geometry (NULL if none) + latest risk (NULL if none) |

Indexes: risk date / status / province (partial on `is_current`), boundary level, crosswalk unit/status. `geo.admin_unit`, `geo.name_alias` and every existing table are not altered. Rollback: `apply_serving_migration.py down` drops only these objects. A fresh `pg_dump` was taken and restore-verified before the live change (`C:\Users\dell\pori_backups\pori_airflow_pre_task26_*.dump`, outside the repository); the restore went into the scratch database `pori_t26_restore_check`, where up → load → down → up was rehearsed and is covered by a test.

## Real data (local PostgreSQL 15.19)

Boundary source: COD-AB Pakistan (OCHA FISS via HDX, WFP SDI), v01, valid_on 2022-09-09, CC BY-IGO, sha256 `dc56da20…ee45c`, not government-certified. Rows: 7 provinces, 160 districts, 167/167 geometries valid by the structural checks (closed rings, finite coordinates, extent, parent, country containment of each interior point, duplicate ids, null/empty). Invalid geometries would be stored with `geometry_valid = false` and excluded from the views, never repaired. Full topology (self-intersection) is **not** checked.

Crosswalk (loaded from the Task 25 artifact): districts 54 exact, 2 alias, **104 unmatched**; provinces 4 exact, 3 alias. Unmatched boundaries are kept and are never attached to a canonical unit. Canonical `geo.admin_unit` is unchanged (77 rows: 1/7/69).

Risk: 1,586 rows served, latest date 2026-09-16, 62 units have a latest row. Status distribution: INSUFFICIENT_DATA 1221, LOW 318, MODERATE 21, HIGH 20, CRITICAL 6; `risk_score` NULL on all rows. Map view: 76 canonical provinces/districts, 63 with geometry, 13 without; 62 with risk, of which 13 have risk but no geometry (e.g. Mangla, Kamra — no matched boundary) and are preserved with `geometry = null`.

## API (read-only; GET only)

`GET /health` (unchanged) · `/api/v1/geography/admin-units` (id, name, level, province, has_geometry) · `/api/v1/geography/boundaries` (filters level, province, source; no geometry) · `/api/v1/risk` (date, province, admin_unit_id, risk_status, limit, offset) · `/api/v1/risk/latest` · `/api/v1/risk/map` (GeoJSON FeatureCollection; properties: admin_unit_id/name, province, risk_status, risk_score, risk_confidence, risk_basis, risk_date, top_risk_domain, data_coverage_pct, calculation_version). Invalid date/status/level → 422; unknown `admin_unit_id` → 404; empty result → 200 empty; database failure → 503 (never a silent empty). `/api/v1/risk` previously served the unpopulated legacy `operational_risk` table; it now serves the Task 23 output. The full-geometry map response is about 5 MB; use `level`, `province` or `include_geometry=false` for lighter calls.

## Not done / limitations

No PostGIS (above). No dashboard map UI (the endpoint is ready for it). Gauge geography is untouched (still 0 eligible stations; no inference was added). Risk data is a point-in-time copy: re-run `scripts/risk/load_risk_serving.py` after the engine runs (rows missing from a newer run are flagged `is_current = false`, not deleted). `geo.admin_unit` covers 69 of 160 boundary districts, so 104 boundary districts remain unmatched.
