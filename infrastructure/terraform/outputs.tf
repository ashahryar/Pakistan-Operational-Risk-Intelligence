output "bucket_name" {
  description = "Name of the PORI raw/analytics S3 bucket."
  value       = aws_s3_bucket.pori_raw_data.id
}

output "bucket_arn" {
  description = "ARN of the PORI raw/analytics S3 bucket -- for a future Databricks Unity Catalog external location IAM role to reference (not created yet, see databricks/resources/README.md)."
  value       = aws_s3_bucket.pori_raw_data.arn
}
