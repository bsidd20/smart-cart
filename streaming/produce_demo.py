"""Publish a stream of synthetic price events to Kafka (requires a running broker).

    python -m streaming.produce_demo [count]

Emits a realistic mix: mostly valid v2 events, some legacy v1 (to exercise schema
upgrade), a few malformed/invalid (to exercise the DLQ), and an occasional late event.
Start the broker first: `docker compose up -d`.
"""

import random
import sys
import time

from streaming import config
from streaming.producer import PriceEventProducer


def _make_event(i: int, rng: random.Random) -> tuple[dict, bool]:
    """Return (event, expect_valid). Some events are intentionally bad/old."""
    base = {
        "event_id": i,
        "store_id": rng.randint(0, 49),
        "product_id": rng.randint(0, 4999),
        "price": round(rng.uniform(0.5, 20.0), 2),
        "observed_at": f"2024-03-{rng.randint(1, 28):02d}T08:00:00",
    }
    roll = rng.random()
    if roll < 0.10:  # legacy v1 event -> consumer upgrades it
        return {"schema_version": 1, **base}, True
    if roll < 0.16:  # invalid price -> DLQ
        return {
            "schema_version": 2,
            **base,
            "price": -1,
            "in_stock": True,
            "currency": "USD",
        }, False
    return {"schema_version": 2, **base, "in_stock": rng.random() < 0.95, "currency": "USD"}, True


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    rng = random.Random(7)
    producer = PriceEventProducer()
    published, refused = 0, 0
    for i in range(count):
        event, expect_valid = _make_event(i, rng)
        try:
            producer.send(event)
            published += 1
        except ValueError:
            refused += 1  # producer-side validation caught it before the topic
    producer.flush()
    print(
        f"published {published} events to '{config.TOPIC_PRICE_EVENTS}' "
        f"({refused} refused by producer validation)"
    )
    time.sleep(0.2)


if __name__ == "__main__":
    main()
