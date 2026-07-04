"""Shared data models for normalized shopping listings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Condition = Literal["new", "used", "refurbished", "open_box", "unknown", "any"]


class SourceStatus(BaseModel):
    name: str
    display_name: str
    available: bool
    requires: list[str] = Field(default_factory=list)
    notes: str | None = None


class Listing(BaseModel):
    id: str
    source: str
    marketplace: str
    title: str
    url: str
    price: float | None = Field(default=None, ge=0)
    currency: str = "USD"
    condition: str = "unknown"
    image_url: str | None = None
    seller: str | None = None
    seller_rating: float | None = None
    location: str | None = None
    shipping: str | None = None
    availability: str | None = None
    posted_at: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)


class DealResult(BaseModel):
    listing: Listing
    deal_score: float = Field(ge=0, le=100)
    rank_reason: str
    warnings: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    searched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    sources_requested: list[str]
    sources_used: list[str]
    source_errors: dict[str, str] = Field(default_factory=dict)
    total_results: int
    listings: list[Listing]


class PriceComparison(BaseModel):
    group_key: str
    title: str
    count: int
    low_price: float | None
    high_price: float | None
    average_price: float | None
    sources: list[str]
    listings: list[Listing]
