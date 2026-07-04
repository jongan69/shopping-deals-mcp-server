"""Search orchestration for the shopping deals MCP tools."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from shopping_deals_mcp.config import settings
from shopping_deals_mcp.models import PriceComparison, SearchResponse, SourceStatus
from shopping_deals_mcp.pricing import (
    dedupe_listings,
    effective_price,
    is_accessory_mismatch,
    is_model_token_mismatch,
    product_key,
    score_deals,
    title_similarity,
)
from shopping_deals_mcp.sources import build_sources


class ShoppingDealsService:
    def __init__(self):
        self.sources = build_sources()

    def source_statuses(self) -> list[SourceStatus]:
        return [source.status() for source in self.sources.values()]

    async def search_products(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        max_results_per_source: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> SearchResponse:
        selected = sources or list(self.sources.keys())
        limit = max_results_per_source or settings.max_results_per_source
        tasks = {}
        source_errors: dict[str, str] = {}

        for source_name in selected:
            source = self.sources.get(source_name)
            if source is None:
                source_errors[source_name] = "Unknown source."
                continue
            status = source.status()
            if not status.available:
                source_errors[source_name] = (
                    "Source is not configured. Requires: " + ", ".join(status.requires)
                )
                continue
            tasks[source_name] = asyncio.create_task(
                source.search(
                    query,
                    max_results=limit,
                    price_min=price_min,
                    price_max=price_max,
                    condition=condition,
                    location=location,
                )
            )

        all_listings = []
        for source_name, task in tasks.items():
            try:
                all_listings.extend(await task)
            except Exception as exc:  # Keep partial results useful.
                source_errors[source_name] = f"{type(exc).__name__}: {exc}"

        listings = dedupe_listings(all_listings)
        listings.sort(
            key=lambda item: (
                is_accessory_mismatch(query, item.title),
                is_model_token_mismatch(query, item.title),
                -title_similarity(query, item.title),
                effective_price(item) is None,
                effective_price(item) or float("inf"),
                item.title,
            )
        )
        return SearchResponse(
            query=query,
            sources_requested=selected,
            sources_used=[name for name in tasks if name not in source_errors],
            source_errors=source_errors,
            total_results=len(listings),
            listings=listings,
        )

    async def find_best_deals(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        max_results: int = 10,
        max_results_per_source: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> dict:
        response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        scored = score_deals(query, response.listings)[:max_results]
        return {
            "query": query,
            "searched_at": response.searched_at,
            "source_errors": response.source_errors,
            "total_results": response.total_results,
            "best_deals": [deal.model_dump() for deal in scored],
        }

    async def find_cheapest_offers(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        max_results: int = 10,
        max_results_per_source: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> dict:
        response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        eligible = [
            listing
            for listing in response.listings
            if effective_price(listing) is not None
            and not is_accessory_mismatch(query, listing.title)
            and not is_model_token_mismatch(query, listing.title)
        ]
        cheapest = sorted(
            eligible,
            key=lambda listing: (effective_price(listing) or float("inf"), listing.title),
        )
        return {
            "query": query,
            "searched_at": response.searched_at,
            "source_errors": response.source_errors,
            "total_results": response.total_results,
            "eligible_results": len(eligible),
            "cheapest_offers": [listing.model_dump() for listing in cheapest[:max_results]],
        }

    async def compare_prices(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        max_results_per_source: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> dict:
        response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        groups = defaultdict(list)
        for listing in response.listings:
            groups[product_key(listing.title) or listing.title.lower()].append(listing)

        comparisons: list[PriceComparison] = []
        for key, listings in groups.items():
            prices = [effective_price(listing) for listing in listings if effective_price(listing) is not None]
            comparisons.append(
                PriceComparison(
                    group_key=key,
                    title=listings[0].title,
                    count=len(listings),
                    low_price=min(prices) if prices else None,
                    high_price=max(prices) if prices else None,
                    average_price=(sum(prices) / len(prices)) if prices else None,
                    sources=sorted({listing.source for listing in listings}),
                    listings=listings,
                )
            )

        comparisons.sort(
            key=lambda item: (
                item.low_price is None,
                item.low_price if item.low_price is not None else float("inf"),
                -item.count,
            )
        )
        return {
            "query": query,
            "searched_at": response.searched_at,
            "source_errors": response.source_errors,
            "comparisons": [comparison.model_dump() for comparison in comparisons],
        }

    async def get_listing_details(self, source: str, listing_id: str) -> dict:
        source_client = self.sources.get(source)
        if source_client is None:
            return {"error": f"Unknown source: {source}"}
        status = source_client.status()
        if not status.available:
            return {"error": "Source is not configured.", "requires": status.requires}
        listing = await source_client.details(listing_id)
        if listing is None:
            return {"error": "Listing details are unavailable for this source or listing."}
        return listing.model_dump()
