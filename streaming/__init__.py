"""Kafka-based streaming ingestion for price events.

The pure logic (schema validation, versioning, DLQ routing, watermarking) lives in
schemas.py and consumer.py and is unit-tested without a broker. The producer/consumer
wiring runs against a Kafka broker started via docker-compose.
"""
