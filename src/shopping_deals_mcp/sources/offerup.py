"""OfferUp public search source."""

from __future__ import annotations

import json
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource


class OfferUpSource(MarketplaceSource):
    name = "offerup"
    display_name = "OfferUp"

    def __init__(self, config: Settings = settings):
        self.config = config

    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=True,
            requires=[],
            notes="Public OfferUp search parser. Results are local and may vary by inferred location.",
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
        url = f"https://offerup.com/search?q={quote_plus(query)}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            timeout=self.config.http_timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        return _parse_offerup_html(response.text, max_results, price_min, price_max)


def _parse_offerup_html(
    html_text: str,
    max_results: int,
    price_min: float | None = None,
    price_max: float | None = None,
) -> list[Listing]:
    soup = BeautifulSoup(html_text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []

    data = json.loads(script.string)
    raw_listings: list[dict] = []
    _collect_modular_feed_listings(data, raw_listings)

    listings: list[Listing] = []
    seen_ids: set[str] = set()
    for item in raw_listings:
        listing_id = str(item.get("listingId") or item.get("id") or "")
        if not listing_id or listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        price = parse_price(item.get("price"))
        if price is not None:
            if price_min is not None and price < price_min:
                continue
            if price_max is not None and price > price_max:
                continue

        image = item.get("image") if isinstance(item.get("image"), dict) else {}
        listings.append(
            Listing(
                id=listing_id,
                source=OfferUpSource.name,
                marketplace="OfferUp",
                title=str(item.get("title") or "").strip(),
                url=f"https://offerup.com/item/detail/{listing_id}",
                price=price,
                currency="USD",
                condition="used",
                image_url=image.get("url"),
                location=item.get("locationName"),
                shipping="Local pickup",
                raw=item,
            )
        )
        if len(listings) >= max_results:
            break

    return [listing for listing in listings if listing.title]


def _collect_modular_feed_listings(obj: object, results: list[dict]) -> None:
    if isinstance(obj, dict):
        if obj.get("__typename") == "ModularFeedListing" and obj.get("title"):
            results.append(obj)
        for value in obj.values():
            _collect_modular_feed_listings(value, results)
    elif isinstance(obj, list):
        for value in obj:
            _collect_modular_feed_listings(value, results)
