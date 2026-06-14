# Dev environment. Remote state in S3 with DynamoDB locking; one module instance.
terraform {
  required_version = ">= 1.5"
  backend "s3" {
    bucket         = "smartcart-tfstate"
    key            = "dev/lakehouse.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "smartcart-tflock"
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "smartcart", environment = "dev" }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

module "lakehouse" {
  source                  = "../../modules/lakehouse"
  environment             = "dev"
  noncurrent_version_days = 7 # short retention in dev to save cost
}

output "lake_bucket" {
  value = module.lakehouse.lake_bucket
}
