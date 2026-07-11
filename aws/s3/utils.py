import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import boto3
from botocore.exceptions import ClientError

from config.aws_config import (
    AWS_REGION,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
)


def get_s3_client():

    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def object_exists(bucket_name, object_key):

    s3 = get_s3_client()

    try:

        s3.head_object(
            Bucket=bucket_name,
            Key=object_key
        )

        return True

    except ClientError:

        return False