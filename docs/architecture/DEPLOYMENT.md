# Deployment (Task 40)

## Target architecture: one host, Docker Compose

The smallest deployment that runs everything the project needs. No Glue, Redshift, Lambda, NAT Gateway or other paid AWS service is involved; S3 archiving is optional and off by default.

```
                 browser
        ┌──────────┴───────────┐
   :8501 dashboard        :8088 Airflow UI              (public ports)
        │                       │
   :8000 api  ◄── dashboard     scheduler + LocalExecutor workers ── extractors ── NDMA / PDMA / PMD sites
        │                       │
        └──────► postgres:15 ◄──┘        (127.0.0.1:5433 on the host only; containers use postgres:5432)
                    │
             named volume postgres-db-volume  (persistent)
```

| Service | Container | Purpose | Health check |
|---|---|---|---|
| `postgres` | `airflow_postgres` | application data, serving schemas, Airflow metadata (PostgreSQL 15, no PostGIS) | `pg_isready` |
| `airflow-init` | `airflow_init` | one-shot: migrate the Airflow metadata, create the admin user | exits 0 |
| `airflow-webserver` | `airflow_webserver` | Airflow UI on :8088 | HTTP `/health` |
| `airflow-scheduler` | `airflow_scheduler` | runs the DAGs (extraction, parsing, loading) | `airflow jobs check` |
| `api` | `pori_api` | read-only FastAPI on :8000 | `/health` (also requires the database) |
| `dashboard` | `pori_dashboard` | Streamlit on :8501 (talks to the API; some pages read the database) | `/_stcore/health` |

Startup order is enforced by `depends_on` health conditions: postgres → airflow-init → webserver / scheduler; postgres → api → dashboard.

## Secrets and configuration

* `.env` (git-ignored, copy from `.env.example`) holds secrets: `AIRFLOW__WEBSERVER__SECRET_KEY`, `POSTGRES_PASSWORD`, `AIRFLOW_ADMIN_PASSWORD`, optional AWS keys and LLM settings. `.env.docker` (tracked) holds only non-secret settings.
* The compose file reads `POSTGRES_PASSWORD` and `AIRFLOW_ADMIN_PASSWORD` from `.env`; the services read `DB_PASSWORD` (same value as `POSTGRES_PASSWORD`) from an optional untracked `.env.deploy`. The defaults (`airflow` / `admin`) are for local development only.
* **Set `POSTGRES_PASSWORD` before the first start of a deployment**: the database is initialised once, on first start. Changing it later needs `ALTER ROLE`, not a restart.
* PostgreSQL is published on `127.0.0.1` only. The API and the dashboard have no authentication of their own: put them behind a reverse proxy or a firewall rule before exposing them beyond a trusted network.
* S3 archiving is off (`PORI_S3_UPLOAD=off` in `.env.docker`). To enable it, put valid keys in `.env` and set `PORI_S3_UPLOAD=auto`; with invalid keys the upload task fails fast with a clear message instead of retrying thousands of files.

## Commands

First start on a new host:

```bash
git clone <repository> && cd Pakistan-Operational-Risk-Intelligence
cp .env.example .env                       # then edit: generate real values for the three secrets
printf 'DB_PASSWORD=<same as POSTGRES_PASSWORD>
' > .env.deploy   # untracked; read by api, dashboard and Airflow
docker compose up -d --build               # postgres, airflow (web + scheduler), api, dashboard
docker compose ps                          # every service should be healthy
curl http://localhost:8000/health          # {"status":"ok","database":true}
```

Create the database objects on a **new** database (an existing deployment already has them; every script is idempotent):

```bash
python scripts/database/create_tables.py && python scripts/database/create_pmd_tables.py
python scripts/database/create_geo_tables.py && python scripts/database/create_risk_tables.py
```

Enable the recurring DAGs (see `AIRFLOW_OPERATIONS.md` for which ones are safe):

```bash
docker exec airflow_webserver airflow dags unpause ndma_pipeline
docker exec airflow_webserver airflow dags unpause pdma_pipeline
docker exec airflow_webserver airflow dags list          # all seven DAGs visible, no import errors
```

Update a running deployment:

```bash
git pull && docker compose up -d --build api dashboard      # rebuild the images that contain code
docker compose restart airflow-scheduler airflow-webserver   # DAG and pipeline code are mounted, not baked
```

Back up before any schema change (project rule): `docker exec airflow_postgres pg_dump -U airflow -d airflow -Fc > ../backup.dump`, then restore into a scratch database to verify it.

## Verified state (2026-10-07)

All six services ran healthy on the developer machine from this configuration, with the data volume persisted across container recreation. This is a single-host Compose deployment, **not** a cloud deployment: no cloud account, VM or paid service was created. The same files run unchanged on any Linux VM with Docker (for example a small EC2 instance); doing so is a separate decision because it incurs cost and needs the host's firewall and TLS to be set up.

## Not part of this deployment

Glue, Redshift and Lambda (retired, ADR-0001); the Databricks scaffolding; PostGIS and pgvector (not installed); a managed PostgreSQL; autoscaling; a reverse proxy and TLS (host-specific).
