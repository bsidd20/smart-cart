# infra (Terraform)

AWS infrastructure for the lakehouse, with per-environment isolation.

```
infra/
  modules/lakehouse/   reusable: S3 lake (versioned, KMS, lifecycle), Glue DB, pipeline IAM role
  envs/dev/            dev instance (short retention, isolated state + bucket)
  envs/prod/           prod instance (long retention)
```

Each environment has its own remote state (`s3://smartcart-tfstate/<env>/...`) with
DynamoDB locking, its own bucket (`smartcart-<env>-lake`), and its own IAM role, so a
change in dev can never touch prod. `stage` is a copy of `dev` with `environment =
"stage"` and its own state key.

```bash
cd infra/envs/dev
terraform init
terraform plan
terraform apply
```

This is the cloud target for the same Delta tables the pipeline writes locally: set
`SMARTCART_LAKE=s3://smartcart-dev-lake` and the pipeline and dbt write to S3 instead
of the local `data/lake`. Not applied in this repo (no cloud account wired); it is the
deployment definition.
