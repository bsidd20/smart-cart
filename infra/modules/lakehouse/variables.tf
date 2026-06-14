variable "project" {
  type        = string
  default     = "smartcart"
  description = "Project name, used to prefix resources."
}

variable "environment" {
  type        = string
  description = "Environment name (dev, stage, prod)."
}

variable "pipeline_principal" {
  type        = string
  default     = "ecs-tasks.amazonaws.com"
  description = "Service principal that runs the pipeline (ECS, MWAA, EMR, etc.)."
}

variable "noncurrent_version_days" {
  type        = number
  default     = 30
  description = "Days to keep noncurrent object versions before expiry."
}
