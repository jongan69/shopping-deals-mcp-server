"""Optional Amazon public HTML search source."""

from __future__ import annotations

from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource


class AmazonSearchSource(MarketplaceSource):
    name = "amazon"
    display_name = "Amazon"

    def __init__(self, config: Settings = settings):
        self.config = config

    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=self.config.enable_amazon_scrape,
            requires=[] if self.config.enable_amazon_scrape else ["SHOPPING_ENABLE_AMAZON_SCRAPE=true"],
            notes="Public HTML parser. Amazon may block automated requests.",
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
        if not self.config.enable_amazon_scrape:
            return []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        url = f"https://www.amazon.com/s?k={quote_plus(query)}"
        async with httpx.AsyncClient(timeout=self.config.http_timeout_seconds, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        listings: list[Listing] = []
        for card in soup.select('[data-component-type="s-search-result"]')[:max_results]:
            asin = card.get("data-asin")
            title_link = card.select_one("a.a-link-normal.s-line-clamp-2")
            title_el = title_link or card.select_one('[data-cy="title-recipe"]') or card.select_one("h2 span")
            href_el = title_link or card.select_one("h2 a")
            price_el = card.select_one(".a-price .a-offscreen")
            image_el = card.select_one("img.s-image")
            rating_el = card.select_one(".a-icon-alt")
            title = _clean_title(title_el.get_text(" ", strip=True) if title_el else "")
            href = href_el.get("href") if href_el else ""
            price = parse_price(price_el.get_text(" ", strip=True) if price_el else None)
            if price is not None:
                if price_min is not None and price < price_min:
                    continue
                if price_max is not None and price > price_max:
                    continue
            listings.append(
                Listing(
                    id=str(asin or href or title),
                    source=self.name,
                    marketplace="Amazon",
                    title=title,
                    url=urljoin("https://www.amazon.com", href),
                    price=price,
                    currency="USD",
                    condition="new",
                    image_url=image_el.get("src") if image_el else None,
                    seller="Amazon",
                    seller_rating=parse_price(rating_el.get_text(" ", strip=True) if rating_el else None),
                    shipping=None,
                    raw={},
                )
            )

        return [listing for listing in listings if listing.title and listing.url]


def _clean_title(value: str) -> str:
    value = value.strip()
    prefixes = [
        "Sponsored Sponsored You’re seeing this ad based on the product’s relevance to your search query. Leave ad feedback ",
        "Sponsored Sponsored You're seeing this ad based on the product's relevance to your search query. Leave ad feedback ",
    ]
    for prefix in prefixes:
        if value.startswith(prefix):
            return value[len(prefix) :].strip()
    return value
