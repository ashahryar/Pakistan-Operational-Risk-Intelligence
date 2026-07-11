"""
aws/glue/create_crawlers.py

Creates AWS Glue Crawlers for all three S3 data zones:
  - raw/     (Bronze layer — original PDFs and JSON)
  - parsed/  (Silver layer — structured JSON)
  - analytics/ (Gold layer — flat analytics datasets)

Each crawler:
  - Runs on a schedule (daily at 07:00 UTC)
  - Writes to the Glue Data Catalog database: pakistan_risk
  - Automatically detects schema evolution
  - Enables Athena queries directly on S3

Prerequisites:
  - .env must have GLUE_ROLE_ARN, S3_BUCKET, AWS credentials
  - Run aws/glue/create_jobs.py first

Run:
  python aws/glue/create_crawlers.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from config.aws_config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

load_dotenv()

BUCKET        = os.getenv("S3_BUCKET")
GLUE_ROLE_ARN = os.getenv("GLUE_ROLE_ARN")
CATALOG_DB    = "pakistan_risk"

# Crawlers: (name, s3_prefix, table_prefix)
CRAWLERS = [
    {
        "name":         "pakistan-risk-raw-crawler",
        "s3_prefix":    f"s3://{BUCKET}/raw/",
        "table_prefix": "raw_",
        "description":  "Crawls raw zone — original PDFs metadata and PMD JSON",
        "schedule":     "cron(0 7 * * ? *)",   # 07:00 UTC daily
    },
    {
        "name":         "pakistan-risk-parsed-crawler",
        "s3_prefix":    f"s3://{BUCKET}/parsed/",
        "table_prefix": "parsed_",
        "description":  "Crawls parsed zone — structured PDMA JSON",
        "schedule":     "cron(30 7 * * ? *)",  # 07:30 UTC daily
    },
    {
        "name":         "pakistan-risk-analytics-crawler",
        "s3_prefix":    f"s3://{BUCKET}/analytics/",
        "table_prefix": "analytics_",
        "description":  "Crawls analytics zone — flat NDMA datasets",
        "schedule":     "cron(0 8 * * ? *)",   # 08:00 UTC daily
    },
]


def get_client():
    return boto3.client(
        "glue",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def ensure_catalog_database(glue):
    """Create the Glue catalog database if it doesn't exist."""
    try:
        glue.get_database(Name=CATALOG_DB)
        print(f"  Catalog database '{CATALOG_DB}' already exists.")
    except glue.exceptions.EntityNotFoundException:
        glue.create_database(
            DatabaseInput={
                "Name":        CATALOG_DB,
                "Description": "Pakistan Operational Risk Intelligence — Data Catalog",
            }
        )
        print(f"  [CREATED] Catalog database: {CATALOG_DB}")


def crawler_exists(glue, name: str) -> bool:
    try:
        glue.get_crawler(Name=name)
        return True
    except glue.exceptions.EntityNotFoundException:
        return False


def create_or_update_crawler(glue, crawler: dict):
    name = crawler["name"]

    config = {
        "Role":          GLUE_ROLE_ARN,
        "DatabaseName":  CATALOG_DB,
        "Description":   crawler["description"],
        "Targets": {
            "S3Targets": [{"Path": crawler["s3_prefix"]}]
        },
        "TablePrefix":   crawler["table_prefix"],
        "SchemaChangePolicy": {
            "UpdateBehavior": "UPDATE_IN_DATABASE",   # auto schema evolution
            "DeleteBehavior": "LOG",
        },
        "RecrawlPolicy": {
            "RecrawlBehavior": "CRAWL_NEW_FOLDERS_ONLY",
        },
        "Schedule": crawler["schedule"],
        "Configuration": '{"Version":1.0,"CrawlerOutput":{"Partitions":{"AddOrUpdateBehavior":"InheritFromTable"}}}',
    }

    if crawler_exists(glue, name):
        glue.update_crawler(Name=name, **config)
        print(f"  [UPDATED] {name}")
    else:
        glue.create_crawler(Name=name, **config)
        print(f"  [CREATED] {name}")


def start_crawlers(glue):
    """Trigger an immediate run of all crawlers after creation."""
    print("\n  Starting initial crawler runs...")
    for crawler in CRAWLERS:
        try:
            glue.start_crawler(Name=crawler["name"])
            print(f"  [STARTED] {crawler['name']}")
        except glue.exceptions.CrawlerRunningException:
            print(f"  [RUNNING] {crawler['name']} already running")
        except ClientError as e:
            print(f"  [WARN] Could not start {crawler['name']}: {e}")


def main():
    if not GLUE_ROLE_ARN:
        print("ERROR: GLUE_ROLE_ARN not set in .env")
        sys.exit(1)

    if not BUCKET:
        print("ERROR: S3_BUCKET not set in .env")
        sys.exit(1)

    glue = get_client()

    print("=" * 60)
    print("CREATING GLUE CRAWLERS")
    print("=" * 60)

    ensure_catalog_database(glue)

    print()
    for crawler in CRAWLERS:
        print(f"  Crawler: {crawler['name']}")
        print(f"    Path : {crawler['s3_prefix']}")
        create_or_update_crawler(glue, crawler)

    start_crawlers(glue)

    print("\n" + "=" * 60)
    print("GLUE CRAWLERS REGISTERED")
    print("=" * 60)
    print(f"  Catalog DB : {CATALOG_DB}")
    print(f"  Crawlers   : {len(CRAWLERS)}")
    for c in CRAWLERS:
        print(f"    {c['name']}")
        print(f"      Path     : {c['s3_prefix']}")
        print(f"      Schedule : {c['schedule']}")
    print()
    print("  Query with Athena:")
    print(f"    SELECT * FROM {CATALOG_DB}.analytics_ndma_casualties LIMIT 10;")
    print("=" * 60)


if __name__ == "__main__":
    main()
