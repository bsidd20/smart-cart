"""Streaming logic tests. These run without a Kafka broker: the pure routing,
schema-versioning, watermark, and DLQ logic is tested directly, and the producer is
tested with an injected fake. Run with `pytest`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from streaming import config, schemas  # noqa: E402
from streaming.consumer import Watermark, process  # noqa: E402
from streaming.dlq import DLQProducer  # noqa: E402
from streaming.producer import PriceEventProducer  # noqa: E402


class FakeProducer:
    def __init__(self):
        self.sent = []

    def send(self, topic, key=None, value=None):
        self.sent.append((topic, key, value))

    def flush(self):
        pass


def _valid_v2(i=1):
    return {
        "schema_version": 2,
        "event_id": i,
        "store_id": 3,
        "product_id": 9,
        "price": 4.5,
        "observed_at": "2024-03-01T08:00:00",
        "in_stock": True,
        "currency": "USD",
    }


def _valid_v1(i=1):
    return {
        "schema_version": 1,
        "event_id": i,
        "store_id": 3,
        "product_id": 9,
        "price": 4.5,
        "observed_at": "2024-03-01T08:00:00",
    }


def test_validate_accepts_known_versions_and_rejects_bad():
    assert schemas.validate(_valid_v2())[0]
    assert schemas.validate(_valid_v1())[0]
    assert not schemas.validate({**_valid_v2(), "price": -1})[0]  # bad price
    assert not schemas.validate({"schema_version": 1, "event_id": 1})[0]  # missing fields
    assert not schemas.validate({**_valid_v2(), "schema_version": 99})[0]  # unknown version


def test_upgrade_v1_to_latest():
    upgraded = schemas.upgrade(_valid_v1())
    assert upgraded["schema_version"] == schemas.LATEST_VERSION
    assert upgraded["in_stock"] is True and upgraded["currency"] == "USD"


def test_process_routes_valid_and_bad_messages():
    route, event = process(schemas.serialize(_valid_v1()))
    assert route == "ok" and event["schema_version"] == 2  # upgraded
    assert process(b"{not json")[0] == "dlq"  # unparseable
    assert process(schemas.serialize({**_valid_v2(), "price": 0}))[0] == "dlq"  # invalid


def test_watermark_flags_late_events():
    wm = Watermark(allowed_lateness_s=60)
    assert wm.observe(1000.0) is False  # first event sets the mark
    assert wm.observe(1100.0) is False  # newer
    assert wm.observe(1000.0) is True  # 100s behind the mark > 60s allowed


def test_producer_validates_before_publishing():
    fake = FakeProducer()
    producer = PriceEventProducer(producer=fake)
    producer.send(_valid_v2(7))
    assert fake.sent[0][0] == config.TOPIC_PRICE_EVENTS
    assert fake.sent[0][1] == 3  # keyed by store_id
    with pytest.raises(ValueError):
        producer.send({**_valid_v2(), "price": -5})


def test_dlq_producer_wraps_record():
    fake = FakeProducer()
    DLQProducer(producer=fake).send({"error": "bad", "event": {}})
    topic, _key, value = fake.sent[0]
    assert topic == config.TOPIC_DLQ and "dlq_at" in value
