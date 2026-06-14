"""Streaming configuration. Broker address comes from the environment so the same
code runs against local docker-compose, CI, or a managed Kafka (MSK / Confluent)."""

import os

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

TOPIC_PRICE_EVENTS = "price-events"
TOPIC_DLQ = "price-events.dlq"

CONSUMER_GROUP = "smartcart-bronze-loader"

# how many partitions the topic is created with (parallelism ceiling for consumers)
PRICE_EVENTS_PARTITIONS = 6
# events whose event time is older than (max_seen - this) are flagged late
ALLOWED_LATENESS_SECONDS = 3600
