import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aws.s3.utils import get_s3_client
from config.aws_config import S3_BUCKET

s3 = get_s3_client()


def download_folder(s3_prefix: str, local_folder: str):

    local_folder = Path(local_folder)
    local_folder.mkdir(parents=True, exist_ok=True)

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=s3_prefix)

    downloaded = 0
    skipped = 0

    print(f"\nDownloading s3://{S3_BUCKET}/{s3_prefix} → {local_folder}\n")

    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            relative = key[len(s3_prefix):].lstrip("/")
            local_path = local_folder / relative

            if local_path.exists():
                print(f"[SKIPPED] {key}")
                skipped += 1
                continue

            local_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                s3.download_file(S3_BUCKET, key, str(local_path))
                print(f"[DOWNLOADED] {key}")
                downloaded += 1
            except Exception as e:
                print(f"[FAILED] {key}: {e}")

    print("\n==============================")
    print(f"Downloaded : {downloaded}")
    print(f"Skipped    : {skipped}")
    print("==============================\n")


if __name__ == "__main__":
    download_folder("raw", "data/raw")
