"""Run the Bronze stream consumer (requires a running broker).

    python -m streaming.run_consumer [max_batches]

Consumes price-events, routes bad records to the DLQ, and upserts valid events into
the streaming Bronze Delta table (idempotent on event_id). Stops after max_batches if
given, otherwise runs until interrupted.
"""

import sys

from streaming.consumer import BronzeStreamConsumer


def main():
    max_batches = int(sys.argv[1]) if len(sys.argv) > 1 else None
    consumer = BronzeStreamConsumer(batch_size=200)
    print("consuming price-events -> Bronze (Ctrl-C to stop)...")
    consumer.run(max_batches=max_batches)


if __name__ == "__main__":
    main()
