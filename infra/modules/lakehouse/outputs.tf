output "lake_bucket" {
  value       = aws_s3_bucket.lake.id
  description = "S3 bucket backing the data lake."
}

output "glue_database" {
  value       = aws_glue_catalog_database.marts.name
  description = "Glue catalog database for the marts."
}

output "pipeline_role_arn" {
  value       = aws_iam_role.pipeline.arn
  description = "IAM role the ingestion pipeline assumes."
}
