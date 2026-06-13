"""App configuration: paths, default location, matching thresholds, and the
weights used by the optimization objective."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"   # lakehouse root (data/lake/{bronze,silver,gold})

# Centre of the synthetic map; stores are scattered around it. A real deployment
# would take the user's location from the request instead.
DEFAULT_USER_LAT = 38.7223
DEFAULT_USER_LON = -9.1393


@dataclass
class MatchConfig:
    # Trust a semantic match above this similarity; otherwise fall back to fuzzy.
    semantic_threshold: float = 0.55
    # Below this score there's no usable match. Kept high enough to reject nonsense
    # substitutions ("spinach" vs "spaghetti") while allowing close ones.
    min_accept_score: float = 0.72


@dataclass
class Weights:
    # objective (lower is better) =
    #   price * basket_price
    # + distance * round_trip_km
    # + substitution * sum(1 - match_score)
    # + store_visit * num_stores
    # + coverage * num_missing_items
    price_weight: float = 1.0
    distance_weight: float = 0.40
    substitution_penalty: float = 6.0   # weak substitutes must be much cheaper to win
    store_visit_penalty: float = 2.50   # fixed cost per extra store
    coverage_penalty: float = 25.0      # large, so items are never dropped to save a little


@dataclass
class Settings:
    match: MatchConfig = field(default_factory=MatchConfig)
    weights: Weights = field(default_factory=Weights)
    max_stores: int = 3
    user_lat: float = DEFAULT_USER_LAT
    user_lon: float = DEFAULT_USER_LON


SETTINGS = Settings()
