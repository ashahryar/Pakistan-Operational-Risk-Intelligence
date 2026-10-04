# Geographic risk map — status (Task 27)

Streamlit page `dashboard/pages/6_Risk_Map.py` shows the national operational-risk map. It consumes only the FastAPI serving layer.

```
Streamlit page -> dashboard/api_client.py (RiskApiClient) -> FastAPI /api/v1/... -> risk.* / geo.* serving tables
                  dashboard/utils/risk_map_helpers.py  (pure reshaping: no risk logic)
```

The page imports no risk-engine, pipeline, ETL, Airflow or database code. API address: `PORI_API_URL` (default `http://localhost:8000`); run the API with `uvicorn api.app.main:app --port 8000`. The API is not part of Docker Compose, so it must be started separately. If it is unreachable the page shows a message and a start hint, not a traceback (also for 404 / 422 / 503 / timeouts).

## Endpoints used
`/api/v1/geography/admin-units` (province list), `/api/v1/risk` (date list and a chosen date's rows, area detail), `/api/v1/risk/latest` (area detail, latest), `/api/v1/risk/map` (GeoJSON). The client also supports `/api/v1/geography/boundaries`. Responses are cached for 5 minutes (`st.cache_data`); a failed call is not kept.

## Map and filters
Plotly `choropleth_map` (Plotly was already a dependency; no new library). Colour = the engine's `risk_status` as served (CRITICAL, HIGH, MODERATE, LOW, INSUFFICIENT_DATA); `NO_RISK_DATA` (grey) is a display category for an area that has a boundary but no risk row in the scope. Filters: administrative level (district default / province), province, risk status, risk date (latest available per area, or a specific date). Level, province and status are sent to the API so only the needed geometry is downloaded (province level ≈ 0.8 MB, district level ≈ 4.7 MB, first load ≈ 5 s, then cached). For a specific date the geometry still comes from `/risk/map` and risk values from `/api/v1/risk?date=…`, merged by `admin_unit_id`.

Summary cards: areas returned, with risk, without geometry, HIGH, CRITICAL, INSUFFICIENT_DATA — counts of the API's own statuses. Area detail shows admin unit, province, risk date, status, basis, confidence, data coverage, top risk domain, signals (unobserved signals show "not observed", never 0), calculation version and risk score.

## Current coverage (local data, latest available date per area)
- District level: 69 canonical districts returned; 55 have a risk row; 56 have a mapped boundary; 13 districts have no boundary and appear under "Risk records without mapped boundary" (all 13 have risk data) — 42 districts are both mapped and have risk.
- Province level: 7 provinces/regions, all with risk and a boundary.
- Latest-per-area statuses at district level: INSUFFICIENT_DATA 52, LOW 2, MODERATE 1; HIGH and CRITICAL appear only on earlier dates (use the date filter), because "latest" is each area's own last date.

## Why some areas have no geometry
`geo.admin_unit` (canonical) has 69 districts; the COD-AB boundary file has 160 (104 unmatched, never force-mapped), and some canonical units have no boundary polygon (e.g. caveated seed units such as Mangla and Kamra, or units created after the 2022 boundary vintage). They keep their risk record and are listed, not dropped.

## Why `risk_score` is null
The Task 23 engine has no evidence-based weights, so it computes no numeric score (v1.0.0); statuses use provisional, non-authoritative thresholds. The page shows the score as unavailable and never derives one.

## Limitations
Native PostGIS is not installed (geometry is validated GeoJSON `jsonb`; no spatial query or spatial index). Boundaries are COD-AB v01 (2022-09-09, CC BY-IGO), third-party and not government-certified. The map shows risk statuses only for areas with a risk row; gauge geography is still unresolved (0 eligible stations), so gauge risk does not contribute. The date list is read from `/api/v1/risk` (limit 2000) and the page warns if that limit is reached. Plotly's base map tiles (Carto/OpenStreetMap) load from the browser, so a map background needs internet access.
