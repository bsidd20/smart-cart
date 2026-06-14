"""Spark + Delta batch transform: Bronze raw_products -> Silver dim_product.

An alternative processing engine to the DuckDB/dbt path, used when data outgrows a
single node. Demonstrates:
  - reading partitioned Delta and pushing a partition filter (partition-aware read),
  - a window-function dedup (latest row per barcode) - the same logic as the dbt model,
    expressed in the Spark DataFrame API,
  - a partitioned Delta write.

Run with spark-submit + the Delta package (see spark/README.md). DuckDB wins on a
laptop; Spark wins once the data no longer fits one machine. Same SQL semantics either
way, which is why the dbt models port unchanged.
"""

import os
import sys

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

BRONZE = os.environ.get("BRONZE_PATH", "/app/data/lake/bronze/raw_products")
SILVER = os.environ.get("SILVER_PATH", "/app/data/lake/silver/dim_product_spark")


def main():
    # optional category filter -> demonstrates partition pruning on a partitioned table
    category = sys.argv[1] if len(sys.argv) > 1 else None

    spark = SparkSession.builder.appName("smartcart-batch-silver").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    bronze = spark.read.format("delta").load(BRONZE)
    if category:
        bronze = bronze.where(F.col("taxonomy_key") == category)  # partition pruning

    latest = Window.partitionBy("barcode").orderBy(F.col("last_modified_t").desc())
    silver = (
        bronze.where((F.length("barcode") > 0) & (F.length("product_name") > 0))
        .withColumn("rn", F.row_number().over(latest))
        .where("rn = 1")
        .select(
            "barcode",
            "product_name",
            "brands",
            F.col("taxonomy_key").alias("category"),
            "last_modified_t",
        )
    )

    (silver.write.format("delta").mode("overwrite").partitionBy("category").save(SILVER))
    print(f"wrote {silver.count()} rows to {SILVER}")


if __name__ == "__main__":
    main()
