"""Publish a stream of synthetic price events to Kafka (requires a running broker).

    python -m streaming.produce_demo [count]

Emits a realistic mix: mostly valid v2 events, some legacy v1 (to exercise schema
upgrade), and some invalid/malformed records sent raw so they reach the topic and are
routed to the DLQ by the consumer. Start the stack first: `docker compose up --build`.
"""

import json
import random
import sys
import time

from streaming import config
from streaming.producer import PriceEventProducer


def _make_event(i: int, rng: random.Random) -> tuple[dict, str]:
    """Return (event, kind) where kind is 'ok', 'v1', or 'bad'."""
    base = {
        "event_id": i,
        "store_id": rng.randint(0, 49),
        "product_id": rng.randint(0, 4999),
        "price": round(rng.uniform(0.5, 20.0), 2),
        "observed_at": f"2024-03-{rng.randint(1, 28):02d}T08:00:00",
    }
    roll = rng.random()
    in_stock = rng.random() < 0.95
    if roll < 0.10:  # legacy v1 -> consumer upgrades it
        return {"schema_version": 1, **base}, "v1"
    v2 = {"schema_version": 2, **base, "in_stock": in_stock, "currency": "USD"}
    if roll < 0.16:  # invalid price -> consumer DLQ
        return {**v2, "price": -1}, "bad"
    return v2, "ok"


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    rng = random.Random(7)

    good = PriceEventProducer()
    # A raw producer for records that must reach the topic to exercise the consumer's
    # DLQ (the validating producer would otherwise refuse them before publishing).
    from kafka import KafkaProducer

    raw = KafkaProducer(
        bootstrap_servers=config.BOOTSTRAP_SERVERS,
        key_serializer=lambda k: str(k).encode(),
        value_serializer=lambda v: v if isinstance(v, bytes) else json.dumps(v).encode(),
    )

    ok = bad = malformed = 0
    for i in range(count):
        event, kind = _make_event(i, rng)
        if kind == "bad":
            raw.send(config.TOPIC_PRICE_EVENTS, key=event["store_id"], value=event)
            bad += 1
        else:
            good.send(event)
            ok += 1
    for _ in range(10):  # unparseable bytes -> DLQ
        raw.send(config.TOPIC_PRICE_EVENTS, key=0, value=b"{ not valid json")
        malformed += 1

    good.flush()
    raw.flush()
    print(
        f"published {ok} valid, {bad} invalid, {malformed} malformed to "
        f"'{config.TOPIC_PRICE_EVENTS}' (invalid + malformed are routed to the DLQ)"
    )
    time.sleep(0.3)


if __name__ == "__main__":
    main()
