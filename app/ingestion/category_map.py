"""Maps our grocery taxonomy to Open Food Facts categories.

Each taxonomy entry drives three things:
  - which OFF category to pull (off_category),
  - a canonical search term added as a synonym so plain queries match ("milk"),
  - a modeled base price + product group used by the (clearly synthetic) pricing
    layer, since OFF has product data but no prices.

OFF has no free price data, so prices are modeled on top of the real product master.
"""
from __future__ import annotations

# taxonomy_key -> config
TAXONOMY: dict[str, dict] = {
    "milk":           {"off_category": "Milks",            "term": "milk",           "group": "dairy",   "base_price": 1.20,
                       "exclude": ["almond", "soy", "oat", "coconut", "cashew", "plant", "rice milk"]},
    "eggs":           {"off_category": "Chicken eggs",     "term": "eggs",           "group": "dairy",   "base_price": 3.00},
    "chicken breast": {"off_category": "Chicken breasts",  "term": "chicken breast", "group": "meat",    "base_price": 7.50},
    "rice":           {"off_category": "Rices",            "term": "rice",           "group": "grains",  "base_price": 3.20},
    "spinach":        {"off_category": "Spinachs",         "term": "spinach",        "group": "produce", "base_price": 2.20},
    "yogurt":         {"off_category": "Yogurts",          "term": "yogurt",         "group": "dairy",   "base_price": 2.80},
    "cheese":         {"off_category": "Cheeses",          "term": "cheese",         "group": "dairy",   "base_price": 3.40},
    "bread":          {"off_category": "Breads",           "term": "bread",          "group": "bakery",  "base_price": 1.90},
    "pasta":          {"off_category": "Pastas",           "term": "pasta",          "group": "grains",  "base_price": 1.30},
    "cereal":         {"off_category": "Breakfast cereals","term": "cereal",         "group": "breakfast","base_price": 3.60},
    "coffee":         {"off_category": "Coffees",          "term": "coffee",         "group": "beverages","base_price": 5.40},
    "orange juice":   {"off_category": "Orange juices",    "term": "orange juice",   "group": "beverages","base_price": 2.40},
}

# product group -> per-chain price multipliers and coverage (specialization)
GROUPS = ["dairy", "meat", "produce", "grains", "bakery", "breakfast", "beverages"]
