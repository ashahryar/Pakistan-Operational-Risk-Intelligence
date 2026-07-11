import os
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


# ==========================================================
# S3 HELPERS
# ==========================================================

def upload_folder(local_folder: str, s3_prefix: str):
    """
    Upload one folder to S3.
    """

    from aws.s3.upload import upload_folder as s3_upload

    result = s3_upload(local_folder, s3_prefix)

    if result["failed"] > 0:
        raise RuntimeError(
            f"S3 upload failed ({result['failed']} files)"
        )

    print(f"[S3] Uploaded {result['uploaded']} files -> {s3_prefix}")

    return result


def upload_all_to_s3():
    """
    Upload all project folders to S3.
    Used by daily DAGs.
    """

    upload_folder("data/raw/ndma", "raw/ndma")
    upload_folder("data/analytics/ndma", "analytics/ndma")

    upload_folder("data/raw/pdma", "raw/pdma")
    upload_folder("data/parsed/pdma", "parsed/pdma")

    upload_folder("data/raw/pmd", "raw/pmd")


def upload_all():
    """
    Upload every data zone.
    Used by weekly DAG.
    """

    from aws.s3.upload import upload_all as s3_upload_all

    return s3_upload_all()


# ==========================================================
# GLUE HELPERS
# ==========================================================

def start_glue_job(job_name: str):
    """
    Start one Glue Job and wait until it finishes.
    """

    glue = boto3.client(
        "glue",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    run_id = glue.start_job_run(
        JobName=job_name
    )["JobRunId"]

    print("=" * 60)
    print(f"Started Glue Job : {job_name}")
    print(f"Run ID           : {run_id}")
    print("=" * 60)

    terminal_states = {
        "SUCCEEDED",
        "FAILED",
        "ERROR",
        "STOPPED",
        "TIMEOUT",
    }

    while True:

        time.sleep(30)

        state = glue.get_job_run(
            JobName=job_name,
            RunId=run_id,
        )["JobRun"]["JobRunState"]

        print(f"[Glue] {job_name}: {state}")

        if state == "SUCCEEDED":
            print(f"[Glue] {job_name} completed successfully.")
            return

        if state in terminal_states:
            raise RuntimeError(
                f"Glue Job '{job_name}' ended with state: {state}"
            )


def start_multiple_glue_jobs(job_names):
    """
    Run multiple Glue Jobs sequentially.
    """

    for job in job_names:
        start_glue_job(job)