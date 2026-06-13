"""Build the lakehouse: raw feeds -> bronze -> silver -> gold.

    python scripts/build_lakehouse.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lakehouse import pipeline  # noqa: E402

if __name__ == "__main__":
    print("Building lakehouse...")
    pipeline.build(verbose=True)
    print("Done.")
