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

**Embedding runtime (Task 30).** `api/Dockerfile` has a build argument `INSTALL_EMBEDDINGS` (Compose: `API_EMBEDDINGS`, default `true`) that adds the ONNX embedding runtime (`requirements/embeddings.txt`) and bakes in the pinned embedding model (~70 MB) so `GET /api/v1/rag/search?mode=semantic` can embed queries without network access at runtime. `API_EMBEDDINGS=false docker compose build api` gives the small lexical-only image, where `mode=semantic` answers 503 (CI uses this to avoid model downloads). Embeddings are *generated* by `scripts/rag/embed_chunks.py`, never by the API.

**Grounded answers (Task 31).** `GET /api/v1/rag/ask` calls a language model only if `PORI_LLM_PROVIDER`, `PORI_LLM_MODEL` and `PORI_LLM_API_KEY` (optional `PORI_LLM_BASE_URL`, `PORI_LLM_TIMEOUT`, `PORI_LLM_MAX_TOKENS`) are set in the API container's environment; otherwise it answers 503 `LLM_UNAVAILABLE` with the retrieved evidence. `GET /api/v1/ml/predictions` and `/api/v1/ml/models` (Task 33) serve the stored ML forecasts read-only (migration 0033, schema `ml`; the image carries only `pipeline/ml/{__init__,contracts}.py`, no scikit-learn). `GET /api/v1/rag/search` responses (Task 35) carry `relevance_status` / `abstained` / `abstention_reason` and a per-result `relevance.assessment` (backward compatible; `only_relevant=true` drops low-relevance rows); the image gains `pipeline/rag/relevance.py` and no dependency. `GET /api/v1/agent/ask` and `/api/v1/agent/tools` (Task 34) serve the read-only operational intelligence agent (see [`AGENT_STATUS.md`](AGENT_STATUS.md)); the image carries the pure `pipeline/agents/*.py` modules and no new dependency. `GET /api/v1/agent/ask` answers 503 `LLM_UNAVAILABLE` (with the structured tool results) when no provider is configured, like the endpoints below. `GET /api/v1/intelligence/ask` (Task 32) uses the same variables and additionally returns the risk-engine context; the API image carries `pipeline/intelligence/*` and the pure canonical geography (`scripts/geo/canonical_data.py`, `resolver.py`) for place detection. No key is stored in the repository or the images; CI sets none.

`api/Dockerfile` (python:3.11-slim, non-root, `requirements/api.txt`: fastapi, uvicorn, pydantic, SQLAlchemy, psycopg2-binary, python-dotenv) contains only `api/app` and `config/database.py`. `dashboard/Dockerfile` uses `requirements/dashboard.txt`. No Airflow, Spark, PostGIS or database server is installed in either image. The PostgreSQL image is still `postgres:15` (no PostGIS).

## Tests

```bash
pytest api/tests tests/dashboard tests/risk tests/db tests/architecture   # API, dashboard, risk, serving DB, stack config
ruff check .
```

`tests/db` has live checks against the local serving tables and skips them when the database is unreachable. CI (`.github/workflows/ci.yml`): `lint-and-test` runs Ruff and the unit suites (no database); `dag-integrity` is unchanged; `serving-stack` builds the API image with the project's Compose file, starts PostgreSQL + API only, builds the geo/serving schema on that empty throwaway database and smoke-tests the endpoint contracts (no AWS, PostGIS or live data).
