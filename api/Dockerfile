# Task 28 -- FastAPI serving layer image. Contains only the API and the DB-connection helper it imports
# (config/database.py) plus the pure RAG runtime modules (pipeline/rag/{contracts,retrieval,evidence,embeddings,semantic}.py): no Airflow, Spark, PostGIS, PostgreSQL server or pipeline code.
# Optional (build arg INSTALL_EMBEDDINGS, default true): the ONNX embedding runtime + the pinned embedding model, so mode=semantic can embed queries.
# With INSTALL_EMBEDDINGS=false the image is the small lexical-only API and mode=semantic answers 503. Build context: repository root.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG INSTALL_EMBEDDINGS=true

COPY requirements/api.txt requirements/embeddings.txt requirements/
RUN pip install -r requirements/api.txt \
 && if [ "$INSTALL_EMBEDDINGS" = "true" ]; then pip install -r requirements/embeddings.txt; fi

COPY api/__init__.py api/__init__.py
COPY api/app api/app
COPY config/__init__.py config/database.py config/
COPY pipeline/__init__.py pipeline/__init__.py
COPY pipeline/rag/__init__.py pipeline/rag/contracts.py pipeline/rag/retrieval.py pipeline/rag/evidence.py pipeline/rag/embeddings.py pipeline/rag/semantic.py pipeline/rag/
ENV PORI_EMBEDDING_CACHE=/app/models
RUN if [ "$INSTALL_EMBEDDINGS" = "true" ]; then python -c "from pipeline.rag.embeddings import ensure_model; print(ensure_model('/app/models'))"; fi

RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000

# DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD come from the environment (config/database.py picks host "postgres" inside Docker).
CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
