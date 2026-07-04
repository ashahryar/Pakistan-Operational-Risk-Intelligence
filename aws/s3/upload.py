import os
from pathlib import Path

from aws.s3.utils import get_s3_client, object_exists
from config.aws_config import S3_BUCKET

s3 = get_s3_client()


def upload_folder(local_folder, s3_prefix):

    local_folder = Path(local_folder)

    if not local_folder.exists():
        print(f"\nFolder not found: {local_folder}")
        return

    uploaded = 0
    skipped = 0

    print("\nUploading files to Amazon S3...\n")

    for root, dirs, files in os.walk(local_folder):

        for file in files:

            local_path = Path(root) / file

            relative_path = local_path.relative_to(local_folder)

            s3_key = f"{s3_prefix}/{relative_path}".replace("\\", "/")

            if object_exists(S3_BUCKET, s3_key):

                print(f"[SKIPPED] {s3_key}")
                skipped += 1
                continue

            try:

                s3.upload_file(
                    str(local_path),
                    S3_BUCKET,
                    s3_key
                )

                print(f"[UPLOADED] {s3_key}")

                uploaded += 1

            except Exception as e:

                print(f"[FAILED] {local_path}")
                print(e)

    print("\n==============================")
    print(f"Uploaded : {uploaded}")
    print(f"Skipped  : {skipped}")
    print("==============================\n")


if __name__ == "__main__":

    upload_folder(
        "data/raw",
        "raw"
    )   