# Task 28 -- Streamlit dashboard image. Reads the serving layer through the API (PORI_API_URL); other pages use the
# existing dashboard/db.py with DB_* environment variables. Build context: repository root.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/dashboard.txt requirements/dashboard.txt
RUN pip install -r requirements/dashboard.txt

COPY dashboard dashboard
COPY config/__init__.py config/database.py config/

RUN useradd --system --uid 10001 --create-home app
USER app

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/Home.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
