# Serving stack — PostgreSQL → FastAPI → Streamlit (Task 28)

The read-only FastAPI serving layer and the Streamlit dashboard run as Docker Compose services next to the existing PostgreSQL service. Airflow is not needed and is not started by these commands.

## Start

```bash
docker compose up -d --build api dashboard
```

This starts `postgres` (if not already running), then `api` (waits for PostgreSQL's health check), then `dashboard` (waits for the API's health check). Ports: API `8000` (`API_PORT` to change), dashboard `8501` (`DASHBOARD_PORT`, e.g. `DASHBOARD_PORT=8502` if a host `streamlit run` already uses 8501).

Database settings come from `.env.docker` (`DB_HOST=postgres`, `DB_PORT=5432`, …; the existing non-secret file). No credentials are written in the Compose file or the images. The serving tables must already exist and be loaded (`db/migrations/0026_*`, `scripts/geo/load_boundaries.py`, `scripts/risk/load_risk_serving.py`); without them the API still starts and answers with empty results.

## Verify

```bash
docker compose ps                                  # api and dashboard report "healthy"
curl http://localhost:8000/health                  # {"status":"ok","database":true}
curl http://localhost:8000/api/v1/risk/latest
curl "http://localhost:8000/api/v1/risk/map?level=1"
```

The API health check (`/health`) passes only if the API answers **and** reports the database reachable; the dashboard check uses Streamlit's `/_stcore/health`.

## How the dashboard finds the API

`dashboard/api_client.py` reads `PORI_API_URL`. In Compose the `dashboard` service sets `PORI_API_URL=http://api:8000` (the service name on the Compose network). A dashboard started on the host (`streamlit run dashboard/Home.py`) keeps the default `http://localhost:8000`, or any URL you export in `PORI_API_URL`.

## Images

`api/Dockerfile` (python:3.11-slim, non-root, `requirements/api.txt`: fastapi, uvicorn, pydantic, SQLAlchemy, psycopg2-binary, python-dotenv) contains only `api/app` and `config/database.py`. `dashboard/Dockerfile` uses `requirements/dashboard.txt`. No Airflow, Spark, PostGIS or database server is installed in either image. The PostgreSQL image is still `postgres:15` (no PostGIS).

## Tests

```bash
pytest api/tests tests/dashboard tests/risk tests/db tests/architecture   # API, dashboard, risk, serving DB, stack config
ruff check .
```

`tests/db` has live checks against the local serving tables and skips them when the database is unreachable. CI (`.github/workflows/ci.yml`): `lint-and-test` runs Ruff and the unit suites (no database); `dag-integrity` is unchanged; `serving-stack` builds the API image with the project's Compose file, starts PostgreSQL + API only, builds the geo/serving schema on that empty throwaway database and smoke-tests the endpoint contracts (no AWS, PostGIS or live data).
