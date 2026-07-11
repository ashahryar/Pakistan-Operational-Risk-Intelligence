# Pakistan Operational Risk Intelligence Platform

# ==========================================
# PROJECT STARTUP
# ==========================================

## Go to project

cd "E:\Playing with code\Pakistan-Operational-Risk-Intelligence"

# ==========================================
# PYTHON VENV
# ==========================================

## Activate

venv\Scripts\activate

## Deactivate

deactivate

# ==========================================
# DOCKER
# ==========================================

## Build

docker compose build

## Start

docker compose up -d

## Start with rebuild

docker compose up --build -d

## Stop

docker compose stop

## Shutdown

docker compose down

## Shutdown and remove volumes

docker compose down -v

## Restart

docker compose restart

## Show running containers

docker ps

## Show all containers

docker ps -a

## Show images

docker images

## Remove unused images

docker image prune -a

# ==========================================
# AIRFLOW
# ==========================================

## Open UI

http://localhost:8080

Username

admin

Password

admin

# ==========================================
# AIRFLOW CONTAINERS
# ==========================================

## Scheduler

docker exec -it airflow_scheduler bash

## Webserver

docker exec -it airflow_webserver bash

## PostgreSQL

docker exec -it airflow_postgres bash

# ==========================================
# AIRFLOW LOGS
# ==========================================

cd /opt/airflow/logs

find .

find /opt/airflow/logs -name "*.log"

cat filename.log

# ==========================================
# AIRFLOW CONFIG
# ==========================================

airflow config list

airflow info

airflow version

airflow dags list

airflow tasks list manual_pipeline

airflow dags list-runs

# ==========================================
# TRIGGER DAGS
# ==========================================

## Manual Pipeline

airflow dags trigger manual_pipeline

## NDMA

airflow dags trigger ndma_pipeline

## PDMA

airflow dags trigger pdma_pipeline

## PMD

airflow dags trigger pmd_pipeline

## Weekly

airflow dags trigger weekly_full_pipeline

# ==========================================
# TRIGGER WITH CONFIG
# ==========================================

NDMA

airflow dags trigger manual_pipeline --conf '{"source":"ndma"}'

PDMA

airflow dags trigger manual_pipeline --conf '{"source":"pdma"}'

PMD

airflow dags trigger manual_pipeline --conf '{"source":"pmd"}'

ALL

airflow dags trigger manual_pipeline --conf '{"source":"all"}'

# ==========================================
# POSTGRESQL
# ==========================================

docker exec -it airflow_postgres psql -U airflow

## Databases

\l

## Tables

\dt

## Describe table

\d table_name

## Count

SELECT COUNT(*) FROM ndma_reports;

SELECT COUNT(*) FROM pdma_reports;

SELECT COUNT(*) FROM pmd_reports;

## Exit

\q

# ==========================================
# DOCKER LOGS
# ==========================================

docker logs airflow_scheduler

docker logs airflow_webserver

docker logs airflow_postgres

Follow logs

docker logs -f airflow_scheduler

# ==========================================
# PROJECT STRUCTURE
# ==========================================

tree /F /A

Save to file

tree /F /A > project_structure.txt

# ==========================================
# GIT
# ==========================================

git status

git add .

git commit -m "message"

git push

git pull

# ==========================================
# STREAMLIT
# ==========================================

streamlit run dashboard/app.py

# ==========================================
# VERIFY PIPELINE
# ==========================================

Step 1

Run DAG

↓

Step 2

Check

data/raw/

↓

Step 3

Check

data/parsed/

↓

Step 4

Check PostgreSQL

↓

Step 5

Check Dashboard

# ==========================================
# AWS (Later)
# ==========================================

S3

Glue

Redshift

CloudWatch

IAM

# ==========================================
# USEFUL COMMANDS
# ==========================================

Current directory

pwd

List files

ls

List all

ls -la

Python version

python --version

Pip packages

pip list

Installed Airflow version

airflow version

Docker version

docker version

Docker compose version

docker compose version

Free ports

netstat -ano

Kill process

taskkill /PID PID_NUMBER /F