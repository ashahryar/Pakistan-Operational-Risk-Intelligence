"""
pipeline/helpers/aws_helper.py

Reusable AWS Helper Functions

Supports

• Amazon S3 Upload
• AWS Glue Jobs
• Future Redshift Support
"""

import os
import time
from pathlib import Path

import boto3

from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
)

from dotenv import load_dotenv


# ==========================================================
# PROJECT ROOT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


# ==========================================================
# AWS CONFIGURATION
# ==========================================================

AWS_REGION = os.getenv("AWS_REGION")

AWS_ACCESS_KEY = os.getenv(
    "AWS_ACCESS_KEY_ID"
)

AWS_SECRET_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY"
)

S3_BUCKET = os.getenv(
    "S3_BUCKET"
)


# ==========================================================
# AWS CLIENTS
# ==========================================================

s3 = boto3.client(

    "s3",

    region_name=AWS_REGION,

    aws_access_key_id=AWS_ACCESS_KEY,

    aws_secret_access_key=AWS_SECRET_KEY,

)

glue = boto3.client(

    "glue",

    region_name=AWS_REGION,

    aws_access_key_id=AWS_ACCESS_KEY,

    aws_secret_access_key=AWS_SECRET_KEY,

)


# ==========================================================
# CONSTANTS
# ==========================================================

GLUE_POLL_INTERVAL = 20

TERMINAL_STATES = {

    "SUCCEEDED",

    "FAILED",

    "ERROR",

    "TIMEOUT",

    "STOPPED",

}
# ==========================================================
# S3 HELPERS
# ==========================================================

def upload_folder(local_folder: str, s3_prefix: str):
    """
    Upload an entire folder to Amazon S3.

    Returns:
        dict
    """

    from aws.s3.upload import upload_folder as s3_upload

    print("=" * 60)
    print(f"Uploading Folder : {local_folder}")
    print(f"S3 Prefix        : {s3_prefix}")
    print("=" * 60)

    try:

        result = s3_upload(

            local_folder,

            s3_prefix,

        )

    except Exception as e:

        raise RuntimeError(

            f"S3 Upload Failed : {e}"

        )

    print(f"Uploaded : {result['uploaded']}")
    print(f"Skipped  : {result['skipped']}")
    print(f"Failed   : {result['failed']}")

    if result["failed"] > 0:

        raise RuntimeError(

            f"{result['failed']} files failed to upload."

        )

    print("=" * 60)

    return result


# ==========================================================
# UPLOAD RAW DATA
# ==========================================================

def upload_raw(local_folder: str, source: str):
    """
    Upload raw dataset.

    Example

    upload_raw("data/raw/pmd","pmd")
    """

    return upload_folder(

        local_folder,

        f"raw/{source}",

    )


# ==========================================================
# UPLOAD ANALYTICS DATA
# ==========================================================

def upload_analytics(local_folder: str, source: str):
    """
    Upload analytics dataset.

    Example

    upload_analytics(
        "data/analytics/pmd",
        "pmd"
    )
    """

    return upload_folder(

        local_folder,

        f"analytics/{source}",

    )


# ==========================================================
# UPLOAD EVERYTHING
# ==========================================================

def upload_all():

    upload_raw(

        "data/raw/ndma",

        "ndma",

    )

    upload_analytics(

        "data/analytics/ndma",

        "ndma",

    )

    upload_raw(

        "data/raw/pdma",

        "pdma",

    )

    upload_analytics(

        "data/analytics/pdma",

        "pdma",

    )

    upload_raw(

        "data/raw/pmd",

        "pmd",

    )

    upload_analytics(

        "data/analytics/pmd",

        "pmd",

    )

    print("=" * 60)
    print("ALL S3 UPLOADS COMPLETED")
    print("=" * 60)

# ==========================================================
# GLUE HELPERS
# ==========================================================

def wait_for_glue_job(job_name: str, run_id: str):
    """
    Wait until Glue Job finishes.
    """

    print("=" * 60)
    print(f"Waiting for Glue Job : {job_name}")
    print("=" * 60)

    while True:

        time.sleep(GLUE_POLL_INTERVAL)

        try:

            response = glue.get_job_run(

                JobName=job_name,

                RunId=run_id,

            )

        except ClientError as e:

            raise RuntimeError(

                f"Unable to fetch Glue status : {e}"

            )

        state = response["JobRun"]["JobRunState"]

        print(f"{job_name} -> {state}")

        if state == "SUCCEEDED":

            print("=" * 60)
            print("Glue Job Completed Successfully")
            print("=" * 60)

            return True

        if state in TERMINAL_STATES:

            raise RuntimeError(

                f"{job_name} finished with state : {state}"

            )


# ==========================================================
# START GLUE JOB
# ==========================================================

def start_glue_job(job_name: str):
    """
    Start Glue Job and wait for completion.
    """

    print("=" * 60)
    print(f"Starting Glue Job : {job_name}")
    print("=" * 60)

    try:

        response = glue.start_job_run(

            JobName=job_name

        )

    except ClientError as e:

        raise RuntimeError(

            f"Glue Job Failed : {e}"

        )

    run_id = response["JobRunId"]

    print(f"Run ID : {run_id}")

    wait_for_glue_job(

        job_name,

        run_id,

    )

    return run_id

# ==========================================================
# START MULTIPLE GLUE JOBS
# ==========================================================

def start_multiple_glue_jobs(job_names):
    """
    Run multiple Glue jobs sequentially.
    """

    if not job_names:
        print("No Glue jobs supplied.")
        return

    print("=" * 60)
    print("STARTING MULTIPLE GLUE JOBS")
    print("=" * 60)

    for job in job_names:

        start_glue_job(job)

    print("=" * 60)
    print("ALL GLUE JOBS COMPLETED")
    print("=" * 60)


# ==========================================================
# S3 VALIDATION
# ==========================================================

def bucket_exists():
    """
    Check whether configured S3 bucket exists.
    """

    try:

        s3.head_bucket(

            Bucket=S3_BUCKET

        )

        return True

    except Exception:

        return False


def check_s3_folder(prefix: str):
    """
    Check whether a folder exists in S3.
    """

    response = s3.list_objects_v2(

        Bucket=S3_BUCKET,

        Prefix=prefix,

        MaxKeys=1,

    )

    return "Contents" in response


# ==========================================================
# VERIFY S3 UPLOAD
# ==========================================================

def verify_upload(prefix: str):
    """
    Verify uploaded files exist in S3.
    """

    print("=" * 60)
    print(f"Checking S3 Folder : {prefix}")
    print("=" * 60)

    if check_s3_folder(prefix):

        print("S3 Verification Successful")

        return True

    raise RuntimeError(

        f"S3 folder not found : {prefix}"

    )


# ==========================================================
# TEST
# ==========================================================

if __name__ == "__main__":

    print("=" * 60)
    print("AWS HELPER TEST")
    print("=" * 60)

    print(f"Region : {AWS_REGION}")
    print(f"Bucket : {S3_BUCKET}")

    if bucket_exists():

        print("Bucket connection successful.")

    else:

        print("Bucket connection failed.")

    print("=" * 60)