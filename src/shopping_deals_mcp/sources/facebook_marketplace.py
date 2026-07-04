"""Experimental Facebook Marketplace public search source."""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

import httpx

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource

FACEBOOK_GRAPHQL_URL = "https://www.facebook.com/api/graphql/"
FACEBOOK_MARKETPLACE_SEARCH_DOC_ID = "7111939778879383"
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
DEFAULT_MARKETPLACE_PATH = "nyc"


class FacebookMarketplaceSource(MarketplaceSource):
    name = "facebook_marketplace"
    display_name = "Facebook Marketplace"

    def __init__(self, config: Settings = settings):
        self.config = config

    def status(self) -> SourceStatus:
        has_default_location = (
            self.config.facebook_marketplace_latitude is not None
            and self.config.facebook_marketplace_longitude is not None
        )
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=True,
            requires=[]
            if has_default_location
            else [
                "location as latitude,longitude or "
                "SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE/LONGITUDE"
            ],
            notes=(
                "Experimental public Facebook Marketplace parser. Requires a local search center "
                "and may fail if Facebook changes or blocks anonymous Marketplace requests."
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
        coordinates = _resolve_coordinates(location, self.config)
        if not coordinates:
            return []

        latitude, longitude = coordinates
        headers = _facebook_headers()
        timeout = max(self.config.http_timeout_seconds, 20.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
        ) as client:
            token, referer = await _fetch_lsd_token(client, query)
            payload = _search_payload(
                query=query,
                latitude=latitude,
                longitude=longitude,
                radius_km=self.config.facebook_marketplace_radius_km,
                max_results=max_results,
                lsd=token,
            )
            response = await client.post(
                FACEBOOK_GRAPHQL_URL,
                data=payload,
                headers={
                    **headers,
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://www.facebook.com",
                    "Referer": referer,
                    "x-fb-lsd": token,
                },
            )
            response.raise_for_status()

        data = _loads_graphql_response(response.text)
        listings = _parse_facebook_marketplace_results(
            data,
            max_results=max_results,
            price_min=price_min,
            price_max=price_max,
        )
        return listings


async def _fetch_lsd_token(client: httpx.AsyncClient, query: str) -> tuple[str, str]:
    urls = [
        f"https://www.facebook.com/marketplace/{DEFAULT_MARKETPLACE_PATH}/search/?query={quote_plus(query)}",
        f"https://www.facebook.com/marketplace/search/?query={quote_plus(query)}",
        "https://www.facebook.com/marketplace/",
    ]
    last_status = ""
    for _ in range(2):
        for url in urls:
            response = await client.get(url)
            response.raise_for_status()
            last_status = f"HTTP {response.status_code} from {response.url}"
            token = _extract_lsd_token(response.text)
            if token:
                return token, str(response.url)
    raise ValueError(f"Facebook Marketplace search token was not present in public page ({last_status}).")


def _facebook_headers() -> dict[str, str]:
    return {
        "User-Agent": MOBILE_USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }


def _extract_lsd_token(html_text: str) -> str | None:
    patterns = [
        r'"LSD",\[\],\{"token":"([^"]+)"',
        r'name="lsd"\s+value="([^"]+)"',
        r'"lsd"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text)
        if match:
            return match.group(1)
    return None


def _search_payload(
    *,
    query: str,
    latitude: float,
    longitude: float,
    radius_km: int,
    max_results: int,
    lsd: str,
) -> dict[str, str]:
    variables = {
        "count": max(1, min(max_results, 24)),
        "params": {
            "bqf": {"callsite": "COMMERCE_MKTPLACE_WWW", "query": query},
            "browse_request_params": {
                "commerce_enable_local_pickup": True,
                "commerce_enable_shipping": True,
                "commerce_search_and_rp_available": True,
                "commerce_search_and_rp_condition": None,
                "commerce_search_and_rp_ctime_days": None,
                "filter_location_latitude": latitude,
                "filter_location_longitude": longitude,
                "filter_price_lower_bound": 0,
                "filter_price_upper_bound": 214748364700,
                "filter_radius_km": radius_km,
            },
            "custom_request_params": {"surface": "SEARCH"},
        },
    }
    return {
        "av": "0",
        "__user": "0",
        "__a": "1",
        "__req": "1",
        "__comet_req": "15",
        "lsd": lsd,
        "jazoest": "21000",
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "CometMarketplaceSearchContentContainerQuery",
        "variables": json.dumps(variables, separators=(",", ":")),
        "server_timestamps": "true",
        "doc_id": FACEBOOK_MARKETPLACE_SEARCH_DOC_ID,
    }


def _loads_graphql_response(response_text: str) -> dict:
    response_text = response_text.removeprefix("for (;;);").strip()
    data = json.loads(response_text)
    if data.get("error"):
        summary = data.get("errorSummary") or data.get("errorDescription") or data["error"]
        raise ValueError(f"Facebook Marketplace search failed: {summary}")
    return data


def _parse_facebook_marketplace_results(
    data: dict,
    *,
    max_results: int,
    price_min: float | None = None,
    price_max: float | None = None,
) -> list[Listing]:
    edges = (
        data.get("data", {})
        .get("marketplace_search", {})
        .get("feed_units", {})
        .get("edges", [])
    )
    listings: list[Listing] = []
    seen_ids: set[str] = set()
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        if not isinstance(node, dict) or node.get("__typename") != "MarketplaceFeedListingStoryObject":
            continue
        item = node.get("listing")
        if not isinstance(item, dict):
            continue

        listing_id = str(item.get("id") or "").strip()
        title = str(item.get("marketplace_listing_title") or item.get("title") or "").strip()
        if not listing_id or not title or listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        price = _listing_price(item)
        if price is not None:
            if price_min is not None and price < price_min:
                continue
            if price_max is not None and price > price_max:
                continue

        image = _listing_image(item)
        listings.append(
            Listing(
                id=listing_id,
                source=FacebookMarketplaceSource.name,
                marketplace="Facebook Marketplace",
                title=title,
                url=f"https://www.facebook.com/marketplace/item/{listing_id}",
                price=price,
                currency="USD",
                condition="used",
                image_url=image,
                location=_listing_location(item),
                shipping=_shipping_text(item),
                availability="pending" if item.get("is_pending") else None,
                raw=item,
            )
        )
        if len(listings) >= max_results:
            break
    return listings


def _listing_price(item: dict) -> float | None:
    listing_price = item.get("listing_price")
    if isinstance(listing_price, dict):
        amount = listing_price.get("amount")
        if amount is not None:
            try:
                return float(amount) / 100
            except (TypeError, ValueError):
                pass
        price = parse_price(listing_price.get("formatted_amount"))
        if price is not None:
            return price
    return parse_price(item.get("price") or item.get("currentPrice"))


def _listing_image(item: dict) -> str | None:
    photo = item.get("primary_listing_photo")
    if isinstance(photo, dict):
        image = photo.get("image")
        if isinstance(image, dict) and image.get("uri"):
            return str(image["uri"])
        if photo.get("uri"):
            return str(photo["uri"])
    return None


def _listing_location(item: dict) -> str | None:
    location = item.get("location")
    if not isinstance(location, dict):
        return None
    reverse = location.get("reverse_geocode")
    if isinstance(reverse, dict):
        city_page = reverse.get("city_page")
        if isinstance(city_page, dict) and city_page.get("display_name"):
            return str(city_page["display_name"])
    city_page = location.get("city_page")
    if isinstance(city_page, dict) and city_page.get("display_name"):
        return str(city_page["display_name"])
    address = location.get("single_line_address")
    return str(address) if address else None


def _shipping_text(item: dict) -> str:
    if item.get("is_shipping_offered"):
        return "Shipping offered"
    return "Local pickup"


def _resolve_coordinates(location: str | None, config: Settings) -> tuple[float, float] | None:
    if location:
        normalized = location.strip()
        match = re.search(
            r"^\s*(?P<lat>-?\d+(?:\.\d+)?)\s*,\s*(?P<lon>-?\d+(?:\.\d+)?)\s*$",
            normalized,
        )
        if match:
            return float(match.group("lat")), float(match.group("lon"))
        city_coordinates = _city_coordinates(normalized)
        if city_coordinates:
            return city_coordinates
    if (
        config.facebook_marketplace_latitude is not None
        and config.facebook_marketplace_longitude is not None
    ):
        return config.facebook_marketplace_latitude, config.facebook_marketplace_longitude
    return None


def _city_coordinates(location: str) -> tuple[float, float] | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", location.lower()).strip()
    aliases = {
        "atlanta": (33.7490, -84.3880),
        "austin": (30.2672, -97.7431),
        "boston": (42.3601, -71.0589),
        "chicago": (41.8781, -87.6298),
        "dallas": (32.7767, -96.7970),
        "denver": (39.7392, -104.9903),
        "houston": (29.7604, -95.3698),
        "las vegas": (36.1716, -115.1391),
        "los angeles": (34.0522, -118.2437),
        "miami": (25.7617, -80.1918),
        "new orleans": (29.9511, -90.0715),
        "new york": (40.7128, -74.0060),
        "new york city": (40.7128, -74.0060),
        "nyc": (40.7128, -74.0060),
        "philadelphia": (39.9526, -75.1652),
        "phoenix": (33.4484, -112.0740),
        "portland": (45.5152, -122.6784),
        "san antonio": (29.4252, -98.4946),
        "san diego": (32.7157, -117.1611),
        "san francisco": (37.7749, -122.4194),
        "sfbay": (37.7749, -122.4194),
        "seattle": (47.6062, -122.3321),
        "washington dc": (38.9072, -77.0369),
    }
    return aliases.get(normalized)
