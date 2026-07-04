import boto3
from botocore.exceptions import ClientError

from config.aws_config import AWS_REGION


def get_s3_client():
    """
    Returns an AWS S3 client.
    """

    return boto3.client(
        "s3",
        region_name=AWS_REGION
    )


def object_exists(bucket_name, object_key):
    """
    Check whether an object already exists in S3.
    """

    s3 = get_s3_client()

    try:
        s3.head_object(
            Bucket=bucket_name,
            Key=object_key
        )
        return True

    except ClientError:
        return False