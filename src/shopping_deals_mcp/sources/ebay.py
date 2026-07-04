"""eBay Browse API source."""

from __future__ import annotations

import base64
import time

import httpx

from shopping_deals_mcp.config import Settings, settings
from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.pricing import parse_price
from shopping_deals_mcp.sources.base import MarketplaceSource


class EbaySource(MarketplaceSource):
    name = "ebay"
    display_name = "eBay"

    def __init__(self, config: Settings = settings):
        self.config = config
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def browse_base_url(self) -> str:
        host = "api.sandbox.ebay.com" if self.config.ebay_use_sandbox else "api.ebay.com"
        return f"https://{host}/buy/browse/v1"

    @property
    def oauth_url(self) -> str:
        host = "api.sandbox.ebay.com" if self.config.ebay_use_sandbox else "api.ebay.com"
        return f"https://{host}/identity/v1/oauth2/token"

    def status(self) -> SourceStatus:
        has_app_token_path = bool(self.config.ebay_app_id and self.config.ebay_cert_id)
        available = bool(self.config.ebay_access_token or has_app_token_path)
        requires = [] if available else ["EBAY_ACCESS_TOKEN or EBAY_APP_ID + EBAY_CERT_ID"]
        return SourceStatus(
            name=self.name,
            display_name=self.display_name,
            available=available,
            requires=requires,
            notes="Uses the official eBay Browse API.",
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
        token = await self._get_access_token()
        if not token:
            return []

        params: dict[str, str] = {
            "q": query,
            "limit": str(min(max_results, 200)),
        }
        filters: list[str] = []
        if price_min is not None or price_max is not None:
            filters.append(
                "price:["
                + (f"{price_min:.2f}" if price_min is not None else "")
                + ".."
                + (f"{price_max:.2f}" if price_max is not None else "")
                + "]"
            )
        if condition != "any":
            condition_ids = _condition_filter(condition)
            if condition_ids:
                filters.append(f"conditions:{{{condition_ids}}}")
        if filters:
            params["filter"] = ",".join(filters)

        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.config.ebay_marketplace_id,
        }
        async with httpx.AsyncClient(timeout=self.config.http_timeout_seconds) as client:
            response = await client.get(
                f"{self.browse_base_url}/item_summary/search",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        listings: list[Listing] = []
        for item in data.get("itemSummaries", [])[:max_results]:
            price = _amount(item.get("price"))
            listings.append(
                Listing(
                    id=str(item.get("itemId") or item.get("legacyItemId") or ""),
                    source=self.name,
                    marketplace="eBay",
                    title=str(item.get("title") or "").strip(),
                    url=str(item.get("itemWebUrl") or ""),
                    price=price,
                    currency=str((item.get("price") or {}).get("currency") or "USD"),
                    condition=_normalize_condition(item.get("condition")),
                    image_url=(item.get("image") or {}).get("imageUrl"),
                    seller=(item.get("seller") or {}).get("username"),
                    seller_rating=parse_price((item.get("seller") or {}).get("feedbackPercentage")),
                    location=_location_text(item.get("itemLocation")),
                    shipping=_shipping_text(item),
                    availability=item.get("buyingOptions", [None])[0],
                    raw=item,
                )
            )

        return [listing for listing in listings if listing.id and listing.title and listing.url]

    async def details(self, listing_id: str) -> Listing | None:
        token = await self._get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.config.ebay_marketplace_id,
        }
        async with httpx.AsyncClient(timeout=self.config.http_timeout_seconds) as client:
            response = await client.get(f"{self.browse_base_url}/item/{listing_id}", headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            item = response.json()

        return Listing(
            id=str(item.get("itemId") or listing_id),
            source=self.name,
            marketplace="eBay",
            title=str(item.get("title") or "").strip(),
            url=str(item.get("itemWebUrl") or ""),
            price=_amount(item.get("price")),
            currency=str((item.get("price") or {}).get("currency") or "USD"),
            condition=_normalize_condition(item.get("condition")),
            image_url=(item.get("image") or {}).get("imageUrl"),
            seller=(item.get("seller") or {}).get("username"),
            seller_rating=parse_price((item.get("seller") or {}).get("feedbackPercentage")),
            location=_location_text(item.get("itemLocation")),
            shipping=_shipping_text(item),
            availability=item.get("estimatedAvailabilities", [{}])[0].get("estimatedAvailabilityStatus"),
            raw=item,
        )

    async def _get_access_token(self) -> str | None:
        if self.config.ebay_access_token:
            return self.config.ebay_access_token

        if not self.config.ebay_app_id or not self.config.ebay_cert_id:
            return None

        now = time.time()
        if self._token and now < self._token_expires_at:
            return self._token

        credentials = f"{self.config.ebay_app_id}:{self.config.ebay_cert_id}".encode()
        headers = {
            "Authorization": f"Basic {base64.b64encode(credentials).decode()}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
        async with httpx.AsyncClient(timeout=self.config.http_timeout_seconds) as client:
            response = await client.post(self.oauth_url, headers=headers, data=data)
            response.raise_for_status()
            payload = response.json()

        self._token = payload.get("access_token")
        self._token_expires_at = now + max(int(payload.get("expires_in", 7200)) - 300, 60)
        return self._token


def _amount(payload: object) -> float | None:
    if isinstance(payload, dict):
        return parse_price(payload.get("value"))
    return parse_price(payload)


def _normalize_condition(value: object) -> str:
    text = str(value or "unknown").lower()
    if "certified" in text or "refurb" in text:
        return "refurbished"
    if "open" in text:
        return "open_box"
    if "used" in text or "pre-owned" in text:
        return "used"
    if "new" in text:
        return "new"
    return "unknown"


def _condition_filter(condition: str) -> str | None:
    return {
        "new": "1000",
        "open_box": "1500",
        "refurbished": "2000,2010,2020,2030",
        "used": "3000",
    }.get(condition)


def _location_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    parts = [
        payload.get("city"),
        payload.get("stateOrProvince"),
        payload.get("country"),
        payload.get("postalCode"),
    ]
    return ", ".join(str(part) for part in parts if part)


def _shipping_text(item: dict) -> str | None:
    options = item.get("shippingOptions") or []
    if not options:
        return None
    option = options[0]
    cost = _amount(option.get("shippingCost"))
    if cost == 0:
        return "Free shipping"
    if cost is not None:
        return f"Shipping ${cost:.2f}"
    return option.get("shippingCostType")
