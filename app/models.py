"""Pydantic models shared across the app.

Store 1--< InventoryItem >--1 Product, then
UserCartItem -> MatchResult -> OptimizationResult.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Store(BaseModel):
    store_id: str
    name: str
    chain: str
    lat: float
    lon: float
    distance_km: Optional[float] = None   # filled in per request


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    brand: Optional[str] = None
    unit: str = "each"
    search_terms: list[str] = Field(default_factory=list)   # synonyms used for matching


class InventoryItem(BaseModel):
    store_id: str
    product_id: str
    price: float
    in_stock: bool = True


class UserCartItem(BaseModel):
    raw_text: str
    quantity: int = 1


class MatchResult(BaseModel):
    query: str
    store_id: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    price: Optional[float] = None
    score: float = 0.0
    method: Literal["semantic", "fuzzy", "none"] = "none"
    available: bool = False


class Assignment(BaseModel):
    item: str
    quantity: int
    store_id: str
    store_name: str
    product_name: str
    unit_price: float
    line_cost: float
    match_score: float
    match_method: str
    reason: str


class OptimizationResult(BaseModel):
    strategy: Literal["single_store", "multi_store"]
    assignments: list[Assignment]
    missing_items: list[str]
    total_cost: float
    num_stores: int
    stores_used: list[str]
    total_distance_km: float
    coverage: float
    objective: float
    explanation: list[str]
