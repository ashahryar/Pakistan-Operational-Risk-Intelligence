FROM apache/airflow:2.9.3-python3.11

USER root

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    && apt-get clean

USER airflow

COPY airflow_requirements.txt /

RUN pip install --no-cache-dir -r /airflow_requirements.txt