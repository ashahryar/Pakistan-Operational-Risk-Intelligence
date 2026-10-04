"""Task 28 -- static checks of the containerised serving stack (Compose, Dockerfiles, requirements, CI). No Docker needed."""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
SERVICES = COMPOSE["services"]
API_DOCKERFILE = (REPO / "api" / "Dockerfile").read_text(encoding="utf-8")
DASH_DOCKERFILE = (REPO / "dashboard" / "Dockerfile").read_text(encoding="utf-8")
CI = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def test_existing_services_and_database_image_are_unchanged():
    assert {"postgres", "airflow-init", "airflow-webserver", "airflow-scheduler"} <= set(SERVICES)
    assert SERVICES["postgres"]["image"] == "postgres:15"                      # PostGIS image deliberately NOT introduced
    assert "postgis" not in (REPO / "docker-compose.yml").read_text(encoding="utf-8").lower()


def test_api_service_is_wired_to_postgres_with_a_real_health_check():
    api = SERVICES["api"]
    assert api["build"]["dockerfile"] == "api/Dockerfile" and any(":8000" in p for p in api["ports"])
    assert api["depends_on"]["postgres"]["condition"] == "service_healthy"       # uses PostgreSQL's own health check, no sleeps
    assert ".env.docker" in api["env_file"]
    hc = " ".join(api["healthcheck"]["test"])
    assert "/health" in hc and "'ok'" in hc and "database" in hc                   # verifies the API answers AND the DB is reachable
    assert "command" not in api or "sleep" not in str(api["command"])


def test_container_database_host_is_the_compose_service_not_localhost():
    env = dict(line.split("=", 1) for line in (REPO / ".env.docker").read_text(encoding="utf-8").splitlines() if "=" in line)
    assert env["DB_HOST"] == "postgres" and env["DB_PORT"] == "5432"
    for name in ("api", "dashboard"):
        assert "localhost" not in str(SERVICES[name].get("environment", {})) and "127.0.0.1" not in str(SERVICES[name].get("environment", {}))


def test_dashboard_reaches_the_api_through_the_compose_network():
    dash = SERVICES["dashboard"]
    assert dash["environment"]["PORI_API_URL"] == "http://api:8000"
    assert dash["depends_on"]["api"]["condition"] == "service_healthy"
    assert "_stcore/health" in " ".join(dash["healthcheck"]["test"])
    assert "${DASHBOARD_PORT:-8501}:8501" in dash["ports"]                         # no clash with a host-run dashboard


def test_no_secrets_are_written_into_compose_for_the_new_services():
    for name in ("api", "dashboard"):
        text = yaml.dump(SERVICES[name]).lower()
        assert "password" not in text and "secret" not in text and "token" not in text


def test_api_image_contains_only_what_the_api_needs():
    assert API_DOCKERFILE.startswith("# Task 28") and "FROM python:3.11-slim" in API_DOCKERFILE
    for forbidden in ("airflow", "pyspark", "postgis", "postgresql-", "apt-get", "node", "kubectl"):
        assert forbidden not in API_DOCKERFILE.lower().replace("no airflow, spark, postgis, postgresql server or pipeline code", "")
    assert "USER app" in API_DOCKERFILE and "EXPOSE 8000" in API_DOCKERFILE
    assert "uvicorn" in API_DOCKERFILE and "api.app.main:app" in API_DOCKERFILE
    copies = [ln for ln in API_DOCKERFILE.splitlines() if ln.startswith("COPY ")]
    assert not any(c.split()[1] in {".", "data", "pipeline", "scripts", "aws"} for c in copies)
    pipeline_files = {f for c in copies for f in c.split()[1:-1] if f.startswith("pipeline/")}
    assert pipeline_files == {"pipeline/__init__.py", "pipeline/rag/__init__.py", "pipeline/rag/contracts.py",
                              "pipeline/rag/retrieval.py", "pipeline/rag/evidence.py", "pipeline/rag/embeddings.py",
                              "pipeline/rag/semantic.py", "pipeline/rag/hybrid.py", "pipeline/rag/llm.py",
                              "pipeline/rag/grounding.py", "pipeline/intelligence/__init__.py", "pipeline/intelligence/context.py",
                              "pipeline/intelligence/risk_context.py", "pipeline/intelligence/assembly.py",
                              "pipeline/intelligence/grounding.py"}       # only the pure RAG / intelligence runtime modules
    scripts_files = {f for c in copies for f in c.split()[1:-1] if f.startswith("scripts/")}
    assert scripts_files == {"scripts/__init__.py", "scripts/geo/__init__.py", "scripts/geo/canonical_data.py", "scripts/geo/resolver.py"}
    assert "USER app" in DASH_DOCKERFILE and "streamlit" in DASH_DOCKERFILE


def test_api_requirements_are_pinned_and_minimal():
    lines = [ln.strip() for ln in (REPO / "requirements" / "api.txt").read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    assert all("==" in ln for ln in lines)
    names = {ln.split("==")[0].lower() for ln in lines}
    assert {"fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary"} <= names
    assert not names & {"apache-airflow", "pyspark", "streamlit", "pandas", "boto3", "scikit-learn"}


def test_dockerignore_keeps_data_env_and_api_tests_out_of_images():
    ign = (REPO / ".dockerignore").read_text(encoding="utf-8").split()
    assert {".env", "data/", "api/tests/"} <= set(ign)


def test_ci_has_a_single_workflow_with_a_serving_stack_job():
    assert [p.name for p in (REPO / ".github" / "workflows").iterdir()] == ["ci.yml"]
    assert {"lint-and-test", "dag-integrity", "serving-stack"} <= set(CI["jobs"])
    job = CI["jobs"]["serving-stack"]
    steps = "\n".join(str(s.get("run", "")) for s in job["steps"])
    assert "docker compose config -q" in steps and "--wait postgres api" in steps and "/health" in steps
    assert "aws" not in steps.lower() and "postgis" not in steps.lower() and "airflow-webserver" not in steps
    assert "pytest tests/ databricks/tests/ api/tests/" in "\n".join(str(s.get("run", "")) for s in CI["jobs"]["lint-and-test"]["steps"])
    assert "plotly" in (REPO / "requirements" / "ci.txt").read_text(encoding="utf-8")        # the map page's tests need it in CI
