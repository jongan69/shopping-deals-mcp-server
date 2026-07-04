"""Google Shopping source powered by SerpApi."""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource


class SerpApiGoogleShoppingSource(MarketplaceSource):
    name = "serpapi_google_shopping"
    display_name = "Google Shopping (SerpApi)"

    def __init__(self, config: Settings = settings):
        self.config = config

    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=bool(self.config.serpapi_api_key),
            requires=[] if self.config.serpapi_api_key else ["SERPAPI_API_KEY"],
            notes="Broad retail aggregator. Best coverage when enabled.",
        )

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
        if not self.config.serpapi_api_key:
            return []

        params = {
            "engine": "google_shopping",
            "q": query,
            "api_key": self.config.serpapi_api_key,
            "hl": "en",
            "gl": "us",
            "num": str(max_results),
        }
        if location:
            params["location"] = location

        url = f"https://serpapi.com/search.json?{urlencode(params)}"
        async with httpx.AsyncClient(timeout=self.config.http_timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        listings: list[Listing] = []
        for item in data.get("shopping_results", [])[:max_results]:
            price = parse_price(item.get("price") or item.get("extracted_price"))
            if price is not None:
                if price_min is not None and price < price_min:
                    continue
                if price_max is not None and price > price_max:
                    continue

            marketplace = str(item.get("source") or "Google Shopping")
            item_id = str(item.get("product_id") or item.get("position") or item.get("link"))
            listings.append(
                Listing(
                    id=item_id,
                    source=self.name,
                    marketplace=marketplace,
                    title=str(item.get("title") or "").strip(),
                    url=str(item.get("link") or item.get("product_link") or ""),
                    price=price,
                    currency="USD",
                    condition=_normalize_condition(item.get("condition") or condition),
                    image_url=item.get("thumbnail"),
                    seller=marketplace,
                    seller_rating=parse_price(item.get("rating")),
                    shipping=item.get("delivery") or item.get("shipping"),
                    availability=item.get("availability"),
                    raw=item,
                )
            )

        return [listing for listing in listings if listing.title and listing.url]


def _normalize_condition(value: object) -> str:
    text = str(value or "unknown").lower()
    if "refurb" in text:
        return "refurbished"
    if "open" in text and "box" in text:
        return "open_box"
    if "used" in text or "pre-owned" in text:
        return "used"
    if "new" in text:
        return "new"
    return "unknown"
