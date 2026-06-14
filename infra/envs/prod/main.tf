# Prod environment. Same module, prod-grade retention, isolated state and bucket.
terraform {
  required_version = ">= 1.5"
  backend "s3" {
    bucket         = "smartcart-tfstate"
    key            = "prod/lakehouse.tfstate"
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
    tags = { project = "smartcart", environment = "prod" }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

module "lakehouse" {
  source                  = "../../modules/lakehouse"
  environment             = "prod"
  noncurrent_version_days = 90 # longer retention in prod
}

output "lake_bucket" {
  value = module.lakehouse.lake_bucket
}
