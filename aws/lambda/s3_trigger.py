"""
aws/lambda/s3_trigger.py

AWS Lambda — S3 Event Trigger → Glue ETL

Triggered automatically when a new file lands in S3.
Routes to the correct Glue job based on the S3 key prefix:

  analytics/ndma/**  →  etl_ndma
  parsed/pdma/**     →  etl_pdma
  raw/pmd/**         →  etl_pmd

Deploy via:
  python aws/lambda/deploy.py

Lambda environment variables (set by deploy.py):
  GLUE_JOB_NDMA, GLUE_JOB_PDMA, GLUE_JOB_PMD
"""

import json
import os
import boto3

glue = boto3.client("glue")

GLUE_JOB_NDMA = os.environ.get("GLUE_JOB_NDMA", "etl_ndma")
GLUE_JOB_PDMA = os.environ.get("GLUE_JOB_PDMA", "etl_pdma")
GLUE_JOB_PMD  = os.environ.get("GLUE_JOB_PMD",  "etl_pmd")

# Only trigger Glue when these specific files land — not on every upload
TRIGGER_KEYS = {
    "analytics/ndma/casualties.json": GLUE_JOB_NDMA,
    "parsed/pdma/":                   GLUE_JOB_PDMA,
    "raw/pmd/reports/daily_forecast/all/latest.json": GLUE_JOB_PMD,
}


def _resolve_job(key: str):
    """Return the Glue job name for a given S3 key, or None."""
    if key.startswith("analytics/ndma/"):
        return GLUE_JOB_NDMA
    if key.startswith("parsed/pdma/"):
        return GLUE_JOB_PDMA
    if key.startswith("raw/pmd/"):
        return GLUE_JOB_PMD
    return None


def _start_glue_job(job_name: str, s3_key: str) -> str:
    response = glue.start_job_run(
        JobName=job_name,
        Arguments={"--triggered_by_key": s3_key},
    )
    run_id = response["JobRunId"]
    print(f"[Lambda] Started '{job_name}'  RunId={run_id}  key={s3_key}")
    return run_id


def lambda_handler(event, context):
    triggered = []

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key    = record["s3"]["object"]["key"]
        print(f"[Lambda] S3 event: s3://{bucket}/{key}")

        job = _resolve_job(key)
        if job:
            run_id = _start_glue_job(job, key)
            triggered.append({"job": job, "run_id": run_id, "key": key})
        else:
            print(f"[Lambda] No Glue job mapped for: {key}")

    return {
        "statusCode": 200,
        "body": json.dumps({"triggered": triggered, "count": len(triggered)}),
    }
