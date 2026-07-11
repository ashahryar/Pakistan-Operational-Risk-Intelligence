import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from aws.s3.upload import upload_folder

if __name__ == "__main__":
    upload_folder("data/parsed", "parsed")
