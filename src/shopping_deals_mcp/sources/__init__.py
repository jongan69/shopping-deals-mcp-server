"""Source registry."""

from __future__ import annotations

from shopping_deals_mcp.config import settings
from shopping_deals_mcp.sources.amazon import AmazonSearchSource
from shopping_deals_mcp.sources.base import MarketplaceSource
from shopping_deals_mcp.sources.craigslist import CraigslistSource
from shopping_deals_mcp.sources.ebay import EbaySource
from shopping_deals_mcp.sources.ebay_public import EbayPublicSearchSource
from shopping_deals_mcp.sources.offerup import OfferUpSource
from shopping_deals_mcp.sources.serpapi import SerpApiGoogleShoppingSource


def build_sources() -> dict[str, MarketplaceSource]:
    source_list: list[MarketplaceSource] = [
        SerpApiGoogleShoppingSource(settings),
        EbaySource(settings),
        EbayPublicSearchSource(settings),
        CraigslistSource(settings),
        OfferUpSource(settings),
        AmazonSearchSource(settings),
    ]
    return {source.name: source for source in source_list}


def available_source_names() -> list[str]:
    return list(build_sources().keys())
