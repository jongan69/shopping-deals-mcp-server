"""No-key eBay public HTML search source."""

from __future__ import annotations

from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource
from shopping_deals_mcp.sources.ebay import _normalize_condition


class EbayPublicSearchSource(MarketplaceSource):
    name = "ebay_public"
    display_name = "eBay Public Search"

    def __init__(self, config: Settings = settings):
        self.config = config

    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=True,
            requires=[],
            notes="No-key public eBay search parser. Use official ebay source when credentials are available.",
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
        url = f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}&_sop=15"
        if price_min is not None:
            url += f"&_udlo={price_min:.2f}"
        if price_max is not None:
            url += f"&_udhi={price_max:.2f}"

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

        soup = BeautifulSoup(response.text, "html.parser")
        listings: list[Listing] = []
        for card in soup.select("li.s-item"):
            title_el = card.select_one(".s-item__title")
            link_el = card.select_one("a.s-item__link")
            price_el = card.select_one(".s-item__price")
            image_el = card.select_one(".s-item__image img")
            shipping_el = card.select_one(".s-item__shipping, .s-item__freeXDays")
            seller_el = card.select_one(".s-item__seller-info-text")
            condition_el = card.select_one(".SECONDARY_INFO")

            title = title_el.get_text(" ", strip=True) if title_el else ""
            if not title or title.lower() == "shop on ebay":
                continue

            price = parse_price(price_el.get_text(" ", strip=True) if price_el else None)
            if price is not None:
                if price_min is not None and price < price_min:
                    continue
                if price_max is not None and price > price_max:
                    continue

            href = link_el.get("href") if link_el else ""
            listing_id = _listing_id_from_url(href) or href or title
            listings.append(
                Listing(
                    id=listing_id,
                    source=self.name,
                    marketplace="eBay",
                    title=title,
                    url=urljoin("https://www.ebay.com", href),
                    price=price,
                    currency="USD",
                    condition=_normalize_condition(
                        condition_el.get_text(" ", strip=True) if condition_el else condition
                    ),
                    image_url=image_el.get("src") or image_el.get("data-src") if image_el else None,
                    seller=seller_el.get_text(" ", strip=True) if seller_el else None,
                    shipping=shipping_el.get_text(" ", strip=True) if shipping_el else None,
                    raw={},
                )
            )
            if len(listings) >= max_results:
                break

        return listings


def _listing_id_from_url(url: str) -> str | None:
    marker = "/itm/"
    if marker not in url:
        return None
    tail = url.split(marker, 1)[1]
    parts = [part for part in tail.split("?")[0].split("/") if part]
    return parts[-1] if parts else None
