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
    http_timeout_seconds: float = _env_float("SHOPPING_HTTP_TIMEOUT_SECONDS", 15.0)
    max_results_per_source: int = _env_int("SHOPPING_MAX_RESULTS_PER_SOURCE", 25)


settings = Settings()
