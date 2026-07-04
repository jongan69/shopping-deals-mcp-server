"""Marketplace source interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shopping_deals_mcp.models import Listing, SourceStatus


class MarketplaceSource(ABC):
    name: str
    display_name: str

    @abstractmethod
    def status(self) -> SourceStatus:
        """Return source availability and configuration requirements."""

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> list[Listing]:
        """Search the source and return normalized listings."""

    async def details(self, listing_id: str) -> Listing | None:
        """Fetch detail for a listing if supported."""
        return None
