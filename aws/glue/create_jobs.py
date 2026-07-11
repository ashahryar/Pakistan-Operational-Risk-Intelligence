"""
aws/glue/create_jobs.py

Uploads Glue ETL scripts to S3 and creates (or updates) all three
Glue jobs: etl_ndma, etl_pdma, etl_pmd.

Prerequisites:
  - .env must contain AWS credentials, S3_BUCKET, and Redshift vars
  - IAM role with AWSGlueServiceRole + S3 + Redshift access

Run:
    python aws/glue/create_jobs.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import boto3
from dotenv import load_dotenv
from config.aws_config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

load_dotenv()

BUCKET          = os.getenv("S3_BUCKET")
REDSHIFT_HOST   = os.getenv("REDSHIFT_HOST")
REDSHIFT_PORT   = os.getenv("REDSHIFT_PORT", "5439")
REDSHIFT_DB     = os.getenv("REDSHIFT_DB", "pakistan_operational_risk")
REDSHIFT_USER   = os.getenv("REDSHIFT_USER")
REDSHIFT_PASS   = os.getenv("REDSHIFT_PASSWORD")
GLUE_ROLE_ARN   = os.getenv("GLUE_ROLE_ARN")   # e.g. arn:aws:iam::123456789:role/GlueRole

REDSHIFT_URL    = f"jdbc:redshift://{REDSHIFT_HOST}:{REDSHIFT_PORT}/{REDSHIFT_DB}"
REDSHIFT_TMP    = f"s3://{BUCKET}/tmp/glue/"
SCRIPTS_S3_PATH = f"s3://{BUCKET}/glue/scripts/"

SCRIPTS_DIR = Path(__file__).parent / "scripts"

JOBS = [
    {
        "name":   "etl_ndma",
        "script": "etl_ndma.py",
        "desc":   "NDMA parsed JSON → Redshift",
    },
    {
        "name":   "etl_pdma",
        "script": "etl_pdma.py",
        "desc":   "PDMA parsed JSON → Redshift",
    },
    {
        "name":   "etl_pmd",
        "script": "etl_pmd.py",
        "desc":   "PMD latest JSON → Redshift",
    },
]


def get_clients():
    creds = dict(
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    return (
        boto3.client("s3",   **creds),
        boto3.client("glue", **creds),
    )


def upload_script(s3, script_name):
    local = SCRIPTS_DIR / script_name
    key   = f"glue/scripts/{script_name}"
    s3.upload_file(str(local), BUCKET, key)
    print(f"  Uploaded s3://{BUCKET}/{key}")
    return f"s3://{BUCKET}/{key}"


def job_exists(glue, name):
    try:
        glue.get_job(JobName=name)
        return True
    except glue.exceptions.EntityNotFoundException:
        return False


def common_job_args(script_s3_path):
    return {
        "Role": GLUE_ROLE_ARN,
        "Command": {
            "Name":           "glueetl",
            "ScriptLocation": script_s3_path,
            "PythonVersion":  "3",
        },
        "DefaultArguments": {
            "--job-language":       "python",
            "--enable-metrics":     "",
            "--S3_BUCKET":          BUCKET,
            "--REDSHIFT_URL":       REDSHIFT_URL,
            "--REDSHIFT_USER":      REDSHIFT_USER,
            "--REDSHIFT_PASSWORD":  REDSHIFT_PASS,
            "--REDSHIFT_TMP_DIR":   REDSHIFT_TMP,
        },
        "GlueVersion":    "4.0",
        "NumberOfWorkers": 2,
        "WorkerType":     "G.1X",
        "Timeout":        30,
    }


def create_or_update_job(glue, job, script_s3_path):
    name = job["name"]
    args = common_job_args(script_s3_path)

    if job_exists(glue, name):
        glue.update_job(JobName=name, JobUpdate=args)
        print(f"  [UPDATED] {name}")
    else:
        glue.create_job(Name=name, Description=job["desc"], **args)
        print(f"  [CREATED] {name}")


def main():
    if not GLUE_ROLE_ARN:
        print("ERROR: GLUE_ROLE_ARN not set in .env")
        print("  Add: GLUE_ROLE_ARN=arn:aws:iam::<account-id>:role/<role-name>")
        sys.exit(1)

    if not REDSHIFT_HOST:
        print("ERROR: REDSHIFT_HOST not set in .env — run aws/redshift/setup.py first")
        sys.exit(1)

    s3, glue = get_clients()

    print("=" * 60)
    print("REGISTERING GLUE JOBS")
    print("=" * 60)

    for job in JOBS:
        print(f"\nJob: {job['name']}")
        script_s3 = upload_script(s3, job["script"])
        create_or_update_job(glue, job, script_s3)

    print("\n" + "=" * 60)
    print("ALL GLUE JOBS REGISTERED")
    print("=" * 60)
    print(f"  etl_ndma  → {REDSHIFT_URL}")
    print(f"  etl_pdma  → {REDSHIFT_URL}")
    print(f"  etl_pmd   → {REDSHIFT_URL}")
    print("=" * 60)


if __name__ == "__main__":
    main()
