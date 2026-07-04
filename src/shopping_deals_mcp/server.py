"""MCP server entrypoint."""

from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP

from shopping_deals_mcp.service import ShoppingDealsService

mcp = FastMCP("Shopping Deals", json_response=True)
service = ShoppingDealsService()


@mcp.tool()
def list_sources() -> dict:
    """List shopping sources and show which credentials or flags are required."""
    return {"sources": [status.model_dump() for status in service.source_statuses()]}


@mcp.tool()
async def search_products(
    query: str,
    sources: list[str] | None = None,
    max_results_per_source: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    condition: str = "any",
    location: str | None = None,
) -> dict:
    """Search enabled shopping platforms and return normalized product listings."""
    response = await service.search_products(
        query,
        sources=sources,
        max_results_per_source=max_results_per_source,
        price_min=price_min,
        price_max=price_max,
        condition=condition,
        location=location,
    )
    return response.model_dump()


@mcp.tool()
async def find_best_deals(
    query: str,
    sources: list[str] | None = None,
    max_results: int = 10,
    max_results_per_source: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    condition: str = "any",
    location: str | None = None,
) -> dict:
    """Search products and rank the strongest deals with reasons and warnings."""
    return await service.find_best_deals(
        query,
        sources=sources,
        max_results=max_results,
        max_results_per_source=max_results_per_source,
        price_min=price_min,
        price_max=price_max,
        condition=condition,
        location=location,
    )


@mcp.tool()
async def find_cheapest_offers(
    query: str,
    sources: list[str] | None = None,
    max_results: int = 10,
    max_results_per_source: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    condition: str = "any",
    location: str | None = None,
) -> dict:
    """Search products and return exact-model offers sorted by shipped total when available."""
    return await service.find_cheapest_offers(
        query,
        sources=sources,
        max_results=max_results,
        max_results_per_source=max_results_per_source,
        price_min=price_min,
        price_max=price_max,
        condition=condition,
        location=location,
    )


@mcp.tool()
async def compare_prices(
    query: str,
    sources: list[str] | None = None,
    max_results_per_source: int | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    condition: str = "any",
    location: str | None = None,
) -> dict:
    """Group comparable listings and report low, high, and average observed prices."""
    return await service.compare_prices(
        query,
        sources=sources,
        max_results_per_source=max_results_per_source,
        price_min=price_min,
        price_max=price_max,
        condition=condition,
        location=location,
    )


@mcp.tool()
async def get_listing_details(source: str, listing_id: str) -> dict:
    """Fetch listing details for sources that support detail lookups."""
    return await service.get_listing_details(source, listing_id)


@mcp.resource("shopping://sources")
def source_resource() -> str:
    """Human-readable shopping source status."""
    lines = ["# Shopping Sources", ""]
    for status in service.source_statuses():
        availability = "available" if status.available else "not configured"
        lines.append(f"- {status.display_name} (`{status.name}`): {availability}")
        if status.requires:
            lines.append(f"  Requires: {', '.join(status.requires)}")
        if status.notes:
            lines.append(f"  Notes: {status.notes}")
    return "\n".join(lines)


@mcp.resource("shopping://deal-scoring")
def deal_scoring_resource() -> str:
    """Explain how deal scoring works."""
    return (
        "# Deal Scoring\n\n"
        "Deals are scored from 0 to 100 using observed price position, title relevance, "
        "source confidence, condition, and shipping hints. Scores are triage signals, not "
        "purchase guarantees. Always verify seller reputation, return policy, warranty, "
        "shipping costs, taxes, and listing authenticity before buying."
    )


@mcp.prompt()
def deal_hunter_prompt(product: str, budget: str = "", location: str = "") -> str:
    """Prompt template for careful shopping research."""
    location_text = f" near {location}" if location else ""
    budget_text = f" under {budget}" if budget else ""
    return (
        f"Find the best current deals for {product}{budget_text}{location_text}. "
        "Search multiple sources, compare exact-model matches separately from similar products, "
        "call out hidden costs, seller or authenticity risks, and explain which listing is the "
        "best value rather than merely the lowest price."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Shopping Deals MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
