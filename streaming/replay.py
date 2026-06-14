"""Replay capability.

Reprocess history by seeking consumers to a wall-clock timestamp or an explicit
offset, instead of relying on the committed group offset. Used to rebuild Bronze after
a bug fix, or to drain the DLQ back through the pipeline once a source issue is fixed.
"""

from __future__ import annotations

from collections.abc import Callable

from streaming import config


def _consumer(bootstrap, topic):
    from kafka import KafkaConsumer

    return KafkaConsumer(
        bootstrap_servers=bootstrap or config.BOOTSTRAP_SERVERS,
        enable_auto_commit=False,
        value_deserializer=lambda b: b,
    )


def replay_from_timestamp(
    ts_ms: int,
    handler: Callable,
    bootstrap=None,
    topic: str = config.TOPIC_PRICE_EVENTS,
    limit: int | None = None,
):
    """Replay every message with timestamp >= ts_ms through `handler`."""
    from kafka import TopicPartition

    c = _consumer(bootstrap, topic)
    parts = [TopicPartition(topic, p) for p in (c.partitions_for_topic(topic) or [])]
    c.assign(parts)
    for tp, off in c.offsets_for_times({tp: ts_ms for tp in parts}).items():
        c.seek(tp, off.offset if off else 0)
    seen = 0
    for msg in c:
        handler(msg)
        seen += 1
        if limit and seen >= limit:
            break
    return seen


def replay_dlq(handler: Callable, bootstrap=None, limit: int | None = None):
    """Drain the DLQ topic from the beginning through `handler` (re-ingest)."""
    from kafka import TopicPartition

    c = _consumer(bootstrap, config.TOPIC_DLQ)
    parts = [
        TopicPartition(config.TOPIC_DLQ, p)
        for p in (c.partitions_for_topic(config.TOPIC_DLQ) or [])
    ]
    c.assign(parts)
    c.seek_to_beginning()
    seen = 0
    for msg in c:
        handler(msg)
        seen += 1
        if limit and seen >= limit:
            break
    return seen
