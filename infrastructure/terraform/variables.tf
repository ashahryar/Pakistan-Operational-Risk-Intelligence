# Task 16A (Phase 1 / ADR-0001). No default assumes a specific AWS
# account -- both variables must be supplied explicitly (via
# terraform.tfvars, -var, or environment variables) before `plan`/
# `apply` would even attempt anything.

variable "aws_region" {
  description = "AWS region for the S3 bucket (matches AWS_REGION already used by pipeline/helpers/aws_helper.py)."
  type        = string
}

variable "bucket_name" {
  description = "Name of the PORI raw/analytics S3 bucket (matches the existing S3_BUCKET env var)."
  type        = string
}
