# Infrastructure — Terraform

**Status: definitions written, NOT applied.** `terraform apply` has not
been run. No AWS resource in this directory has been provisioned by
it. This exists so the project's one piece of real, intended AWS
infrastructure — the S3 raw/analytics bucket already used by
`aws/s3/upload.py` — has a reproducible, reviewable definition instead
of having been created by hand (or not tracked as code at all).

## Scope — deliberately narrow

Per Task 16A (Phase 1 / ADR-0001):

**In scope:**
- The S3 bucket (or a reference to the existing one, if it already
  exists — see "Existing bucket" below) and its safe baseline
  configuration (versioning, default encryption, public-access block).

**Explicitly out of scope, not defined anywhere in this directory:**
- AWS Glue (removed from the architecture entirely, Task 16A)
- Amazon Redshift / Redshift Serverless (removed from the architecture entirely, Task 16A)
- NAT Gateway, VPC, or any networking resource
- EKS, ECS, or any container orchestration
- Lambda functions
- IAM roles beyond what a future Databricks Unity Catalog external
  location genuinely requires (not defined yet — see
  `databricks/resources/README.md`)

## Existing bucket

The `S3_BUCKET` environment variable already used by
`pipeline/helpers/aws_helper.py`/`aws/s3/upload.py` may already point
at a real, existing bucket outside Terraform's management. **This
task does not import or take over management of an existing bucket**
(Part N of Task 16A: no AWS resource changes). If/when this Terraform
config is actually applied, the first real step is `terraform import`
against the existing bucket (if one exists), not a fresh `aws_s3_bucket`
creation that could collide with it.

## Files

- `main.tf` — provider + the S3 bucket resource definition (safe
  defaults: versioning enabled, default SSE-S3 encryption, all public
  access blocked).
- `variables.tf` — inputs (bucket name, AWS region), no defaults that
  assume a specific account.
- `outputs.tf` — the bucket name/ARN, for other tools (or a future
  Databricks Unity Catalog external location) to reference.

## Running this (when actually ready to)

```bash
cd infrastructure/terraform
terraform init
terraform plan   # review carefully -- especially whether it proposes
                  # to CREATE a new bucket vs. matching an imported one
# terraform apply -- NOT run as part of Task 16A or any CI workflow
```

No CI workflow in `.github/workflows/` runs `terraform apply` or
`terraform plan` against real credentials — Part H of Task 16A is
explicit that CI does not deploy to paid AWS resources.
