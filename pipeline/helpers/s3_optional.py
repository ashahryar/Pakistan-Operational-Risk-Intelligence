"""Task 40 -- S3 archiving that is explicit about its state.

The pipelines archive raw and parsed files to S3 (the project's only active AWS footprint). That archive must be a visible, honest step:
  * PORI_S3_UPLOAD=off (or false/0)   -> the task is SKIPPED with that reason (archiving deliberately disabled);
  * credentials not configured        -> SKIPPED, naming what is missing;
  * credentials configured            -> one cheap identity check first (STS GetCallerIdentity, read-only). Rejected credentials FAIL the task immediately
                                         with a clear message, instead of retrying thousands of individual uploads;
  * credentials valid                 -> exactly the existing `aws_helper.upload_folder`.
Skipped is not success: the run shows the step as skipped. Nothing about the AWS account or architecture changes here.
Settings are read from the process environment and, like `aws_helper`, from the project's `.env`.
"""

from __future__ import annotations

import os
from pathlib import Path

REQUIRED_ENV = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION", "S3_BUCKET")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _settings(env=None) -> dict:
    if env is not None:
        return dict(env)
    merged = {}
    try:
        from dotenv import dotenv_values
        merged.update({k: v for k, v in dotenv_values(PROJECT_ROOT / ".env").items() if v})
    except Exception:       # python-dotenv missing or .env unreadable: the process environment alone decides
        pass
    merged.update({k: v for k, v in os.environ.items() if v})
    return merged


def s3_state(env=None) -> tuple[str, str]:
    """-> ("disabled" | "unconfigured" | "enabled", reason). Pure given `env`."""
    s = _settings(env)
    if str(s.get("PORI_S3_UPLOAD", "auto")).strip().lower() in ("off", "false", "0", "no"):
        return "disabled", "PORI_S3_UPLOAD is off"
    missing = [k for k in REQUIRED_ENV if not str(s.get(k) or "").strip()]
    if missing:
        return "unconfigured", "missing " + ", ".join(missing)
    return "enabled", "credentials configured"


def check_credentials(env=None) -> None:
    """Raise RuntimeError if AWS rejects the configured credentials. Read-only (sts:GetCallerIdentity)."""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    s = _settings(env)
    try:
        boto3.client("sts", region_name=s["AWS_REGION"], aws_access_key_id=s["AWS_ACCESS_KEY_ID"],
                     aws_secret_access_key=s["AWS_SECRET_ACCESS_KEY"]).get_caller_identity()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "ClientError")
        raise RuntimeError(f"S3 archiving is enabled but AWS rejected the credentials ({code}). Rotate the keys in .env, or set PORI_S3_UPLOAD=off "
                           "to disable archiving. Nothing was uploaded.") from None
    except BotoCoreError as e:
        raise RuntimeError(f"S3 archiving is enabled but AWS could not be reached ({type(e).__name__}). Nothing was uploaded.") from None


def upload_folder_or_skip(local_folder: str, s3_prefix: str):
    state, reason = s3_state()
    if state != "enabled":
        from airflow.exceptions import AirflowSkipException
        raise AirflowSkipException(f"S3 upload skipped ({state}: {reason}). Nothing was uploaded.")
    check_credentials()
    from pipeline.helpers.aws_helper import upload_folder
    return upload_folder(local_folder, s3_prefix)
