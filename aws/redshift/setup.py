"""
aws/redshift/setup.py

Provisions a Redshift Serverless workgroup + namespace
(free-tier eligible, no cluster to manage).

Run once:
    python aws/redshift/setup.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import boto3
from config.aws_config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY

# ----------------------------------------------------------
# CONFIGURATION  — edit these before first run
# ----------------------------------------------------------
NAMESPACE   = "pakistan-risk-ns"
WORKGROUP   = "pakistan-risk-wg"
DB_NAME     = "pakistan_operational_risk"
ADMIN_USER  = "admin"
ADMIN_PASS  = "Admin1234!"          # min 8 chars, upper+lower+digit
BASE_RPU    = 8                     # minimum Redshift Serverless RPU


def get_client():
    return boto3.client(
        "redshift-serverless",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def namespace_exists(client):
    try:
        client.get_namespace(namespaceName=NAMESPACE)
        return True
    except client.exceptions.ResourceNotFoundException:
        return False


def workgroup_exists(client):
    try:
        client.get_workgroup(workgroupName=WORKGROUP)
        return True
    except client.exceptions.ResourceNotFoundException:
        return False


def create_namespace(client):
    print(f"Creating namespace: {NAMESPACE}")
    client.create_namespace(
        namespaceName=NAMESPACE,
        dbName=DB_NAME,
        adminUsername=ADMIN_USER,
        adminUserPassword=ADMIN_PASS,
    )
    print("  Namespace created.")


def create_workgroup(client):
    print(f"Creating workgroup: {WORKGROUP}")
    client.create_workgroup(
        workgroupName=WORKGROUP,
        namespaceName=NAMESPACE,
        baseCapacity=BASE_RPU,
        publiclyAccessible=True,
    )
    print("  Workgroup created. Waiting for AVAILABLE status...")
    _wait_for_workgroup(client)


def _wait_for_workgroup(client):
    for _ in range(40):
        resp = client.get_workgroup(workgroupName=WORKGROUP)
        status = resp["workgroup"]["status"]
        print(f"  Status: {status}")
        if status == "AVAILABLE":
            endpoint = resp["workgroup"]["endpoint"]["address"]
            port     = resp["workgroup"]["endpoint"]["port"]
            print(f"\n  Endpoint : {endpoint}")
            print(f"  Port     : {port}")
            print(f"  DB       : {DB_NAME}")
            print(f"  User     : {ADMIN_USER}")
            print("\n  Add to .env:")
            print(f"  REDSHIFT_HOST={endpoint}")
            print(f"  REDSHIFT_PORT={port}")
            print(f"  REDSHIFT_DB={DB_NAME}")
            print(f"  REDSHIFT_USER={ADMIN_USER}")
            print(f"  REDSHIFT_PASSWORD={ADMIN_PASS}")
            return
        time.sleep(15)
    print("  Timed out waiting. Check AWS Console.")


def main():
    client = get_client()

    print("=" * 60)
    print("REDSHIFT SERVERLESS SETUP")
    print("=" * 60)

    if namespace_exists(client):
        print(f"Namespace '{NAMESPACE}' already exists — skipping.")
    else:
        create_namespace(client)

    if workgroup_exists(client):
        print(f"Workgroup '{WORKGROUP}' already exists — skipping.")
        resp = client.get_workgroup(workgroupName=WORKGROUP)
        endpoint = resp["workgroup"]["endpoint"]["address"]
        port     = resp["workgroup"]["endpoint"]["port"]
        print(f"  Endpoint : {endpoint}:{port}")
    else:
        create_workgroup(client)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
