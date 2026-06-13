"""Generate the synthetic store/catalog/inventory dataset. Idempotent (seeded)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data import simulator  # noqa: E402

if __name__ == "__main__":
    simulator.write_dataset(seed=42, n_stores=8)
