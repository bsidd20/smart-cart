"""Spark Structured Streaming: Kafka price-events -> Bronze Delta.

Fault tolerance + exactly-once:
  - checkpointing records Kafka offsets + state, so a restart resumes exactly where it
    stopped (no loss, no double-count of offsets),
  - the sink is an idempotent Delta MERGE on event_id inside foreachBatch, so even if a
    batch is retried the row is upserted, not duplicated.
  - withWatermark bounds state for late events.

Runs in the Spark container: `docker compose --profile spark up` (see docker-compose.yml).
"""

import os

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9094")
TOPIC = os.environ.get("KAFKA_TOPIC", "price-events")
BRONZE = os.environ.get("BRONZE_PATH", "/app/data/lake/bronze/stream_price_events")
CHECKPOINT = os.environ.get("CHECKPOINT_PATH", "/app/data/lake/_checkpoints/stream_bronze")

EVENT_SCHEMA = StructType(
    [
        StructField("schema_version", IntegerType()),
        StructField("event_id", LongType()),
        StructField("store_id", IntegerType()),
        StructField("product_id", IntegerType()),
        StructField("price", DoubleType()),
        StructField("observed_at", StringType()),
        StructField("in_stock", BooleanType()),
        StructField("currency", StringType()),
    ]
)


def upsert_to_bronze(batch_df, _batch_id):
    from delta.tables import DeltaTable

    spark = batch_df.sparkSession
    deduped = batch_df.dropDuplicates(["event_id"])
    if DeltaTable.isDeltaTable(spark, BRONZE):
        (
            DeltaTable.forPath(spark, BRONZE)
            .alias("t")
            .merge(deduped.alias("s"), "t.event_id = s.event_id")
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        deduped.write.format("delta").partitionBy("event_date").save(BRONZE)


def main():
    spark = SparkSession.builder.appName("smartcart-stream-bronze").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", BOOTSTRAP)
        .option("subscribe", TOPIC)
        .option("startingOffsets", "earliest")
        .load()
    )

    parsed = (
        raw.select(F.from_json(F.col("value").cast("string"), EVENT_SCHEMA).alias("e"))
        .select("e.*")
        .withColumn("event_ts", F.to_timestamp("observed_at"))
        .withColumn("event_date", F.to_date("event_ts"))
        .withWatermark("event_ts", "1 hour")  # bound state for late events
    )

    query = (
        parsed.writeStream.foreachBatch(upsert_to_bronze)
        .option("checkpointLocation", CHECKPOINT)
        .outputMode("update")
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()
