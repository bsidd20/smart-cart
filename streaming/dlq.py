"""Dead-letter queue producer.

Bad records (unparseable, schema-invalid) are published to a separate DLQ topic with
the failure reason and a timestamp, instead of being dropped or blocking the stream.
They can be inspected, fixed at the source, and replayed.
"""

from __future__ import annotations

import json
import time

from streaming import config


class DLQProducer:
    def __init__(self, bootstrap=None, producer=None):
        if producer is not None:
            self._p = producer
        else:
            from kafka import KafkaProducer

            self._p = KafkaProducer(
                bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=5,
            )

    def send(self, record: dict, key=None):
        payload = {**record, "dlq_at": int(time.time())}
        return self._p.send(config.TOPIC_DLQ, key=key, value=payload)

    def flush(self):
        self._p.flush()
