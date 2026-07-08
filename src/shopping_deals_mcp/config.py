"""Runtime configuration for the shopping deals MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class Settings:
    serpapi_api_key: str = os.getenv("SERPAPI_API_KEY", "")
    ebay_access_token: str = os.getenv("EBAY_ACCESS_TOKEN", "")
    ebay_app_id: str = os.getenv("EBAY_APP_ID", "")
    ebay_cert_id: str = os.getenv("EBAY_CERT_ID", "")
    ebay_dev_id: str = os.getenv("EBAY_DEV_ID", "")
    ebay_marketplace_id: str = os.getenv("EBAY_MARKETPLACE_ID", "EBAY_US")
    ebay_use_sandbox: bool = _env_bool("EBAY_USE_SANDBOX", False)
    craigslist_sites: tuple[str, ...] = tuple(
        site.strip()
        for site in os.getenv(
            "CRAIGSLIST_SITES", "newyork,sfbay,losangeles,chicago,houston"
        ).split(",")
        if site.strip()
    )
    enable_amazon_scrape: bool = _env_bool("SHOPPING_ENABLE_AMAZON_SCRAPE", False)
    facebook_marketplace_latitude: float | None = _env_optional_float(
        "SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE"
    )
    facebook_marketplace_longitude: float | None = _env_optional_float(
        "SHOPPING_FACEBOOK_MARKETPLACE_LONGITUDE"
    )
    facebook_marketplace_radius_km: int = _env_int("SHOPPING_FACEBOOK_MARKETPLACE_RADIUS_KM", 16)
    http_timeout_seconds: float = _env_float("SHOPPING_HTTP_TIMEOUT_SECONDS", 15.0)
    max_results_per_source: int = _env_int("SHOPPING_MAX_RESULTS_PER_SOURCE", 25)
    estimated_tax_rate_percent: float | None = _env_optional_float(
        "SHOPPING_ESTIMATED_TAX_RATE_PERCENT"
    )
    tax_shipping_by_default: bool = _env_bool("SHOPPING_TAX_SHIPPING", True)
    resale_store_path: str = os.getenv(
        "SHOPPING_RESALE_STORE_PATH",
        ".shopping-deals/resale-business.json",
    )


settings = Settings()
