"""Price-event producer.

Publishes to the price-events topic, keyed by store_id so all events for a store land
on the same partition and stay ordered. Validates before publishing so malformed
events never enter the stream. acks=all + retries give at-least-once delivery; the
consumer's idempotent sink removes the resulting duplicate risk.
"""

from __future__ import annotations

from streaming import config, schemas


class PriceEventProducer:
    def __init__(self, bootstrap=None, producer=None):
        if producer is not None:
            self._p = producer
        else:
            from kafka import KafkaProducer

            self._p = KafkaProducer(
                bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS,
                key_serializer=lambda k: str(k).encode("utf-8"),
                value_serializer=schemas.serialize,
                acks="all",
                retries=5,
            )

    def send(self, event: dict):
        ok, err = schemas.validate(event)
        if not ok:
            raise ValueError(f"refusing to publish invalid event: {err}")
        return self._p.send(config.TOPIC_PRICE_EVENTS, key=event["store_id"], value=event)

    def flush(self):
        self._p.flush()
