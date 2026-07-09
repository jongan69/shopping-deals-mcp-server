"""OfferUp public search source."""

from __future__ import annotations

import json
import re
from urllib.parse import quote, quote_plus

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
            notes=(
                "Public OfferUp search parser. Defaults to Miami Beach and supports "
                "location overrides through OfferUp's location cookie."
            ),
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
        offerup_location = _resolve_offerup_location(location, self.config)
        params = f"q={quote_plus(query)}&radius={self.config.offerup_radius_miles}"
        url = f"https://offerup.com/search?{params}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": f"ou.location={quote(json.dumps(offerup_location, separators=(',', ':')))}",
        }
        async with httpx.AsyncClient(
            timeout=self.config.http_timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        return _parse_offerup_html(response.text, max_results, price_min, price_max)


def _resolve_offerup_location(location: str | None, config: Settings) -> dict:
    if location:
        coordinates = _coordinates_from_location(location)
        if coordinates:
            city, state, zip_code, latitude, longitude = coordinates
            return {
                "city": city,
                "state": state,
                "zipCode": zip_code,
                "longitude": longitude,
                "latitude": latitude,
                "source": "user",
            }
    return {
        "city": config.offerup_default_city,
        "state": config.offerup_default_state,
        "zipCode": config.offerup_default_zip,
        "longitude": config.offerup_default_longitude,
        "latitude": config.offerup_default_latitude,
        "source": "default",
    }


def _coordinates_from_location(location: str) -> tuple[str, str, str, float, float] | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", location.lower()).strip()
    aliases: dict[str, tuple[str, str, str, float, float]] = {
        "miami beach": ("Miami Beach", "FL", "33139", 25.7907, -80.1300),
        "miami beach fl": ("Miami Beach", "FL", "33139", 25.7907, -80.1300),
        "miami": ("Miami", "FL", "33131", 25.7617, -80.1918),
        "miami fl": ("Miami", "FL", "33131", 25.7617, -80.1918),
        "fort lauderdale": ("Fort Lauderdale", "FL", "33301", 26.1224, -80.1373),
        "fort lauderdale fl": ("Fort Lauderdale", "FL", "33301", 26.1224, -80.1373),
        "orlando": ("Orlando", "FL", "32801", 28.5383, -81.3792),
        "orlando fl": ("Orlando", "FL", "32801", 28.5383, -81.3792),
        "tampa": ("Tampa", "FL", "33602", 27.9506, -82.4572),
        "tampa fl": ("Tampa", "FL", "33602", 27.9506, -82.4572),
        "new york": ("New York", "NY", "10001", 40.7128, -74.0060),
        "new york ny": ("New York", "NY", "10001", 40.7128, -74.0060),
        "nyc": ("New York", "NY", "10001", 40.7128, -74.0060),
        "los angeles": ("Los Angeles", "CA", "90012", 34.0522, -118.2437),
        "los angeles ca": ("Los Angeles", "CA", "90012", 34.0522, -118.2437),
        "atlanta": ("Atlanta", "GA", "30303", 33.7490, -84.3880),
        "atlanta ga": ("Atlanta", "GA", "30303", 33.7490, -84.3880),
        "chicago": ("Chicago", "IL", "60601", 41.8781, -87.6298),
        "chicago il": ("Chicago", "IL", "60601", 41.8781, -87.6298),
    }
    if normalized in aliases:
        return aliases[normalized]
    found = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", location)
    if found:
        latitude = float(found.group(1))
        longitude = float(found.group(2))
        return ("Custom", "US", "00000", latitude, longitude)
    return None


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
