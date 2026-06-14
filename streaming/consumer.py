"""Bronze stream consumer: Kafka -> validate/version/route -> Bronze Delta.

`process()` is pure (bytes in, route + record out) so it is unit-tested without a
broker. `BronzeStreamConsumer` wires it to Kafka with manual offset commits
(at-least-once) and an idempotent Delta MERGE sink keyed on event_id, which makes the
end-to-end behaviour effectively exactly-once even if a message is redelivered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from streaming import config, dlq, schemas


@dataclass
class Watermark:
    """Tracks the max event time seen and flags events that arrive too late."""

    max_event_ts: float = 0.0
    allowed_lateness_s: float = config.ALLOWED_LATENESS_SECONDS

    def observe(self, event_ts: float) -> bool:
        late = self.max_event_ts > 0 and event_ts < (self.max_event_ts - self.allowed_lateness_s)
        self.max_event_ts = max(self.max_event_ts, event_ts)
        return late


def _event_ts(event: dict) -> float:
    try:
        return datetime.fromisoformat(str(event["observed_at"]).replace("Z", "")).timestamp()
    except Exception:
        return 0.0


def process(raw: bytes, watermark: Watermark | None = None) -> tuple[str, dict]:
    """Route one message. Returns ('ok', event) or ('dlq', record). No broker needed."""
    try:
        event = schemas.deserialize(raw)
    except Exception as exc:  # malformed JSON -> DLQ
        return "dlq", {"error": f"deserialize: {exc}", "raw": raw.decode("utf-8", "replace")}
    ok, err = schemas.validate(event)
    if not ok:
        return "dlq", {"error": err, "event": event}
    event = schemas.upgrade(event)
    if watermark is not None:
        event["_late"] = watermark.observe(_event_ts(event))
    return "ok", event


def delta_sink(batch: list[dict]) -> None:
    """Idempotent sink: upsert the batch into the streaming Bronze table on event_id."""
    import pandas as pd

    from app.ingestion import io, paths

    df = pd.DataFrame(batch).astype({"event_id": "int64"}, errors="ignore")
    io.upsert_delta(df, paths.BRONZE_STREAM_EVENTS, key="event_id")


class BronzeStreamConsumer:
    def __init__(
        self, bootstrap=None, group=None, sink=delta_sink, dlq_producer=None, batch_size=500
    ):
        from kafka import KafkaConsumer

        self.consumer = KafkaConsumer(
            config.TOPIC_PRICE_EVENTS,
            bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS,
            group_id=group or config.CONSUMER_GROUP,
            enable_auto_commit=False,  # commit only after the sink succeeds
            auto_offset_reset="earliest",
            value_deserializer=lambda b: b,
        )
        self.dlq = dlq_producer or dlq.DLQProducer(bootstrap)
        self.sink = sink
        self.batch_size = batch_size
        self.watermark = Watermark()

    def run(self, max_batches: int | None = None) -> None:
        batch, done = [], 0
        for msg in self.consumer:
            route, record = process(msg.value, self.watermark)
            if route == "dlq":
                self.dlq.send(record, key=msg.key)
            else:
                batch.append(record)
            if len(batch) >= self.batch_size:
                self.sink(batch)  # write first...
                self.consumer.commit()  # ...then commit offsets (at-least-once)
                batch, done = [], done + 1
                if max_batches and done >= max_batches:
                    return
        if batch:
            self.sink(batch)
            self.consumer.commit()
