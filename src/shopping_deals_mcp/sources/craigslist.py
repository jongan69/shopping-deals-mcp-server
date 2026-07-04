"""Craigslist RSS source for local used deals."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

import httpx

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource


class CraigslistSource(MarketplaceSource):
    name = "craigslist"
    display_name = "Craigslist"

    def __init__(self, config: Settings = settings):
        self.config = config

    def status(self) -> SourceStatus:
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=bool(self.config.craigslist_sites),
            requires=[],
            notes=f"Configured sites: {', '.join(self.config.craigslist_sites)}",
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
        sites = [location] if location else list(self.config.craigslist_sites)
        sites = [site for site in sites if site]
        if not sites:
            return []

        per_site_limit = max(1, max_results // len(sites))
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            timeout=self.config.http_timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            responses = await _gather_sites(client, sites, query, per_site_limit, price_min, price_max)

        listings: list[Listing] = []
        for site, text in responses:
            listings.extend(_parse_rss(site, text, max_results))

        listings = [
            listing
            for listing in listings
            if (price_min is None or listing.price is None or listing.price >= price_min)
            and (price_max is None or listing.price is None or listing.price <= price_max)
        ]
        return listings[:max_results]


async def _gather_sites(
    client: httpx.AsyncClient,
    sites: list[str],
    query: str,
    per_site_limit: int,
    price_min: float | None,
    price_max: float | None,
) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for site in sites:
        params = {
            "query": query,
            "format": "rss",
            "sort": "date",
        }
        if price_min is not None:
            params["min_price"] = str(int(price_min))
        if price_max is not None:
            params["max_price"] = str(int(price_max))
        url = f"https://{site}.craigslist.org/search/sss?{urlencode(params)}"
        response = await client.get(url)
        response.raise_for_status()
        results.append((site, response.text[: per_site_limit * 5000]))
    return results


def _parse_rss(site: str, rss_text: str, max_results: int) -> list[Listing]:
    root = ET.fromstring(rss_text)
    channel = root.find("channel")
    if channel is None:
        return []

    listings: list[Listing] = []
    for item in channel.findall("item")[:max_results]:
        title = html.unescape((item.findtext("title") or "").strip())
        link = item.findtext("link") or ""
        description = html.unescape(item.findtext("description") or "")
        price = parse_price(title) or parse_price(description)
        listing_id = link.rstrip("/").split("/")[-1].split(".")[0] if link else title
        listings.append(
            Listing(
                id=listing_id,
                source=CraigslistSource.name,
                marketplace=f"Craigslist {site}",
                title=title,
                url=link,
                price=price,
                currency="USD",
                condition="used",
                location=site,
                shipping="Local pickup",
                posted_at=item.findtext("pubDate"),
                raw={"description": description},
            )
        )
    return [listing for listing in listings if listing.title and listing.url]
