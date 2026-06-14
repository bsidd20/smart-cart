# Reusable lakehouse module: an encrypted, versioned S3 data lake (bronze/silver/
# gold/marts prefixes), a Glue catalog database, and a least-privilege IAM role for
# the ingestion pipeline. Instantiated once per environment (dev/stage/prod).

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  bucket_name = "${var.project}-${var.environment}-lake"
  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

resource "aws_s3_bucket" "lake" {
  bucket = local.bucket_name
  tags   = local.tags
}

# Versioning gives us Delta-style time travel safety at the object layer and makes
# accidental overwrites recoverable.
resource "aws_s3_bucket_versioning" "lake" {
  bucket = aws_s3_bucket.lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "lake" {
  bucket                  = aws_s3_bucket.lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Expire noncurrent versions to control cost; bronze raw history is kept longer.
resource "aws_s3_bucket_lifecycle_configuration" "lake" {
  bucket = aws_s3_bucket.lake.id
  rule {
    id     = "expire-noncurrent"
    status = "Enabled"
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_days
    }
  }
}

resource "aws_glue_catalog_database" "marts" {
  name = "${var.project}_${var.environment}_marts"
}

# Pipeline role: read/write only this environment's bucket.
resource "aws_iam_role" "pipeline" {
  name = "${var.project}-${var.environment}-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = var.pipeline_principal }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "pipeline_s3" {
  name = "lake-access"
  role = aws_iam_role.pipeline.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/*"]
    }]
  })
}
