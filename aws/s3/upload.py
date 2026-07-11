"""
aws/s3/upload.py

Uploads a local data folder to S3 idempotently.
Skips files that already exist in S3 (checked via HEAD request).

Usage:
    python aws/s3/upload.py                    # uploads data/raw → s3://bucket/raw/
    python aws/s3/upload.py parsed             # uploads data/parsed → s3://bucket/parsed/
    python aws/s3/upload.py analytics          # uploads data/analytics → s3://bucket/analytics/
    python aws/s3/upload.py all                # uploads all three
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aws.s3.utils import get_s3_client, object_exists
from config.aws_config import S3_BUCKET

FOLDERS = {
    "raw":       ("data/raw",       "raw"),
    "parsed":    ("data/parsed",    "parsed"),
    "analytics": ("data/analytics", "analytics"),
}


def upload_folder(local_folder: str, s3_prefix: str) -> dict:
    """
    Upload all files under local_folder to s3://S3_BUCKET/s3_prefix/.
    Returns {"uploaded": int, "skipped": int, "failed": int}
    """
    s3           = get_s3_client()
    local_folder = Path(local_folder)

    if not local_folder.exists():
        print(f"[WARN] Folder not found, skipping: {local_folder}")
        return {"uploaded": 0, "skipped": 0, "failed": 0}

    uploaded = skipped = failed = 0

    print(f"\n{'='*60}")
    print(f"Uploading  {local_folder}  →  s3://{S3_BUCKET}/{s3_prefix}/")
    print(f"{'='*60}")

    for root, _, files in os.walk(local_folder):
        for file in sorted(files):
            local_path = Path(root) / file
            relative   = local_path.relative_to(local_folder)
            s3_key     = f"{s3_prefix}/{relative}".replace("\\", "/")

            if object_exists(S3_BUCKET, s3_key):
                print(f"  [SKIP]   {s3_key}")
                skipped += 1
                continue

            try:
                s3.upload_file(str(local_path), S3_BUCKET, s3_key)
                print(f"  [UP]     {s3_key}")
                uploaded += 1
            except Exception as e:
                print(f"  [FAIL]   {s3_key}  —  {e}")
                failed += 1

    print(f"\n  Uploaded : {uploaded}")
    print(f"  Skipped  : {skipped}")
    print(f"  Failed   : {failed}")
    print(f"{'='*60}\n")

    return {"uploaded": uploaded, "skipped": skipped, "failed": failed}


def upload_all() -> None:
    totals = {"uploaded": 0, "skipped": 0, "failed": 0}
    for local, prefix in FOLDERS.values():
        result = upload_folder(local, prefix)
        for k in totals:
            totals[k] += result[k]

    print(f"\n{'='*60}")
    print("TOTAL UPLOAD SUMMARY")
    print(f"{'='*60}")
    print(f"  Uploaded : {totals['uploaded']}")
    print(f"  Skipped  : {totals['skipped']}")
    print(f"  Failed   : {totals['failed']}")
    print(f"{'='*60}\n")

    if totals["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "raw"

    if target == "all":
        upload_all()
    elif target in FOLDERS:
        local, prefix = FOLDERS[target]
        upload_folder(local, prefix)
    else:
        print(f"Unknown target '{target}'. Use: raw | parsed | analytics | all")
        sys.exit(1)
