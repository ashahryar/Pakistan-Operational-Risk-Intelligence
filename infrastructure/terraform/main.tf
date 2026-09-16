# Task 16A (Phase 1 / ADR-0001). NOT APPLIED -- see README.md.
#
# Defines only the S3 bucket already used by aws/s3/upload.py, with a
# safe baseline configuration. No Glue, no Redshift, no networking, no
# compute -- see README.md's "Scope" section for the full list of what
# is deliberately absent.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "pori_raw_data" {
  bucket = var.bucket_name

  # Never destroy this bucket via `terraform destroy` by accident --
  # raw acquisition artifacts are, per CLAUDE.md rule 1, often
  # irreplaceable (shallow government-site archives).
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "pori_raw_data" {
  bucket = aws_s3_bucket.pori_raw_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pori_raw_data" {
  bucket = aws_s3_bucket.pori_raw_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "pori_raw_data" {
  bucket = aws_s3_bucket.pori_raw_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Logical layout documented for reference (Task 16A Part B item 9) --
# Terraform does not create prefixes/"folders" (S3 has none; they are
# just key prefixes, created implicitly by aws/s3/upload.py's existing
# upload logic, not by this config):
#
#   s3://<bucket>/raw/{ndma,pdma,pmd,suparco,epa,ffc,other_sources}/
#   s3://<bucket>/manifests/
#   s3://<bucket>/acquisition_logs/
#   s3://<bucket>/analytics/
