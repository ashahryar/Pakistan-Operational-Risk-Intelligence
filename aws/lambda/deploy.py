"""
aws/lambda/deploy.py

Deploys the s3_trigger Lambda function and attaches S3 bucket
notifications so it fires automatically on new uploads.

Prerequisites:
  - .env must have AWS credentials, S3_BUCKET, LAMBDA_ROLE_ARN
  - IAM role needs: AWSLambdaBasicExecutionRole + glue:StartJobRun

Add to .env:
  LAMBDA_ROLE_ARN=arn:aws:iam::<account-id>:role/<role-name>

Run:
  python aws/lambda/deploy.py
"""

import io
import json
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from config.aws_config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

load_dotenv()

BUCKET          = os.getenv("S3_BUCKET")
LAMBDA_ROLE_ARN = os.getenv("LAMBDA_ROLE_ARN")
FUNCTION_NAME   = "pakistan-risk-s3-trigger"
RUNTIME         = "python3.11"
HANDLER         = "s3_trigger.lambda_handler"
TIMEOUT         = 30   # seconds
MEMORY          = 128  # MB

SCRIPT = Path(__file__).parent / "s3_trigger.py"

# S3 prefixes that should trigger the Lambda
NOTIFICATION_PREFIXES = [
    "analytics/ndma/",
    "parsed/pdma/",
    "raw/pmd/reports/daily_forecast/",
]


def get_clients():
    creds = dict(
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    return (
        boto3.client("lambda", **creds),
        boto3.client("s3",     **creds),
    )


def build_zip() -> bytes:
    """Package s3_trigger.py into a zip bytes object."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SCRIPT, "s3_trigger.py")
    return buf.getvalue()


def function_exists(lam, name: str) -> bool:
    try:
        lam.get_function(FunctionName=name)
        return True
    except lam.exceptions.ResourceNotFoundException:
        return False


def deploy_function(lam) -> str:
    """Create or update the Lambda function. Returns the function ARN."""
    zip_bytes = build_zip()
    env_vars = {
        "GLUE_JOB_NDMA": "etl_ndma",
        "GLUE_JOB_PDMA": "etl_pdma",
        "GLUE_JOB_PMD":  "etl_pmd",
    }

    if function_exists(lam, FUNCTION_NAME):
        print(f"  Updating function code: {FUNCTION_NAME}")
        lam.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=zip_bytes,
        )
        lam.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Environment={"Variables": env_vars},
            Timeout=TIMEOUT,
            MemorySize=MEMORY,
        )
        resp = lam.get_function(FunctionName=FUNCTION_NAME)
        arn  = resp["Configuration"]["FunctionArn"]
        print(f"  [UPDATED] {FUNCTION_NAME}")
    else:
        print(f"  Creating function: {FUNCTION_NAME}")
        resp = lam.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime=RUNTIME,
            Role=LAMBDA_ROLE_ARN,
            Handler=HANDLER,
            Code={"ZipFile": zip_bytes},
            Environment={"Variables": env_vars},
            Timeout=TIMEOUT,
            MemorySize=MEMORY,
            Description="Pakistan Risk — S3 upload → Glue ETL trigger",
        )
        arn = resp["FunctionArn"]
        print(f"  [CREATED] {FUNCTION_NAME}")

    print(f"  ARN: {arn}")
    return arn


def add_s3_permission(lam, function_arn: str):
    """Allow S3 to invoke the Lambda function."""
    statement_id = "AllowS3Invoke"
    try:
        lam.remove_permission(
            FunctionName=FUNCTION_NAME,
            StatementId=statement_id,
        )
    except ClientError:
        pass

    lam.add_permission(
        FunctionName=FUNCTION_NAME,
        StatementId=statement_id,
        Action="lambda:InvokeFunction",
        Principal="s3.amazonaws.com",
        SourceArn=f"arn:aws:s3:::{BUCKET}",
    )
    print(f"  S3 invoke permission added.")


def attach_s3_notifications(s3, function_arn: str):
    """
    Attach S3 bucket notifications for each prefix.
    Replaces any existing notification config on this bucket.
    """
    configs = [
        {
            "LambdaFunctionArn": function_arn,
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {
                    "FilterRules": [
                        {"Name": "prefix", "Value": prefix}
                    ]
                }
            },
        }
        for prefix in NOTIFICATION_PREFIXES
    ]

    s3.put_bucket_notification_configuration(
        Bucket=BUCKET,
        NotificationConfiguration={"LambdaFunctionConfigurations": configs},
    )
    print(f"  S3 notifications attached for {len(configs)} prefixes:")
    for p in NOTIFICATION_PREFIXES:
        print(f"    s3://{BUCKET}/{p}*")


def main():
    if not LAMBDA_ROLE_ARN:
        print("ERROR: LAMBDA_ROLE_ARN not set in .env")
        print("  Add: LAMBDA_ROLE_ARN=arn:aws:iam::<account-id>:role/<role-name>")
        sys.exit(1)

    lam, s3 = get_clients()

    print("=" * 60)
    print("DEPLOYING LAMBDA: s3_trigger")
    print("=" * 60)

    function_arn = deploy_function(lam)
    add_s3_permission(lam, function_arn)
    attach_s3_notifications(s3, function_arn)

    print("\n" + "=" * 60)
    print("LAMBDA DEPLOYED SUCCESSFULLY")
    print("=" * 60)
    print(f"  Function : {FUNCTION_NAME}")
    print(f"  ARN      : {function_arn}")
    print(f"  Bucket   : {BUCKET}")
    print("  Triggers :")
    for p in NOTIFICATION_PREFIXES:
        print(f"    s3://{BUCKET}/{p}*  →  Glue ETL")
    print("=" * 60)
    print("\nAdd to .env if not already set:")
    print("  LAMBDA_ROLE_ARN=<your-role-arn>")
    print("=" * 60)


if __name__ == "__main__":
    main()
