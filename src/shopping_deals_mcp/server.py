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
    tax_rate_percent: float | None = None,
    tax_on_shipping: bool | None = None,
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
        tax_rate_percent=tax_rate_percent,
        tax_on_shipping=tax_on_shipping,
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
    tax_rate_percent: float | None = None,
    tax_on_shipping: bool | None = None,
) -> dict:
    """Search products and return exact-model offers sorted by shipped total plus estimated tax."""
    return await service.find_cheapest_offers(
        query,
        sources=sources,
        max_results=max_results,
        max_results_per_source=max_results_per_source,
        price_min=price_min,
        price_max=price_max,
        condition=condition,
        location=location,
        tax_rate_percent=tax_rate_percent,
        tax_on_shipping=tax_on_shipping,
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


@mcp.tool()
async def get_ebay_sold_comps(
    query: str,
    max_results: int = 20,
    condition: str = "any",
) -> dict:
    """Estimate resale value from eBay comps.

    Current implementation returns active eBay listing comps as a clearly labeled proxy. It does
    not fabricate true sold-listing data when a sold-comps provider is unavailable.
    """
    return await service.get_ebay_sold_comps(
        query,
        max_results=max_results,
        condition=condition,
    )


@mcp.tool()
def calculate_resale_profit(
    purchase_price: float,
    expected_sale_price: float,
    inbound_shipping: float = 0.0,
    outbound_shipping: float = 0.0,
    purchase_tax_rate_percent: float | None = None,
    platform_fee_percent: float = 13.25,
    promoted_listing_percent: float = 0.0,
    payment_fixed_fee: float = 0.40,
    packing_cost: float = 2.0,
    misc_cost: float = 0.0,
    buyer_shipping_charged: float = 0.0,
) -> dict:
    """Calculate net profit, ROI, break-even sale price, and target buy price."""
    return service.calculate_resale_profit(
        purchase_price=purchase_price,
        expected_sale_price=expected_sale_price,
        inbound_shipping=inbound_shipping,
        outbound_shipping=outbound_shipping,
        purchase_tax_rate_percent=purchase_tax_rate_percent,
        platform_fee_percent=platform_fee_percent,
        promoted_listing_percent=promoted_listing_percent,
        payment_fixed_fee=payment_fixed_fee,
        packing_cost=packing_cost,
        misc_cost=misc_cost,
        buyer_shipping_charged=buyer_shipping_charged,
    )


@mcp.tool()
async def find_arbitrage_opportunities(
    query: str,
    buy_sources: list[str] | None = None,
    max_results: int = 10,
    max_results_per_source: int | None = None,
    location: str | None = None,
    condition: str = "any",
    price_max: float | None = None,
    min_profit: float = 25.0,
    min_roi_percent: float = 20.0,
    purchase_tax_rate_percent: float | None = None,
    outbound_shipping: float = 0.0,
    platform_fee_percent: float = 13.25,
    promoted_listing_percent: float = 0.0,
    packing_cost: float = 2.0,
) -> dict:
    """Find buy-side listings that may be profitable to flip on eBay."""
    return await service.find_arbitrage_opportunities(
        query,
        buy_sources=buy_sources,
        max_results=max_results,
        max_results_per_source=max_results_per_source,
        location=location,
        condition=condition,
        price_max=price_max,
        min_profit=min_profit,
        min_roi_percent=min_roi_percent,
        purchase_tax_rate_percent=purchase_tax_rate_percent,
        outbound_shipping=outbound_shipping,
        platform_fee_percent=platform_fee_percent,
        promoted_listing_percent=promoted_listing_percent,
        packing_cost=packing_cost,
    )


@mcp.tool()
def draft_ebay_listing(
    product_title: str,
    condition: str = "used",
    known_defects: str | None = None,
    included_accessories: str | None = None,
    comp_summary: dict | None = None,
) -> dict:
    """Draft an eBay title, description, pricing hint, and photo/disclosure checklist."""
    return service.draft_ebay_listing(
        product_title=product_title,
        condition=condition,
        known_defects=known_defects,
        included_accessories=included_accessories,
        comp_summary=comp_summary,
    )


@mcp.tool()
def save_resale_lead(lead: dict) -> dict:
    """Save an arbitrage lead into the local reseller pipeline."""
    return service.save_resale_lead(lead)


@mcp.tool()
def update_resale_lead_status(lead_id: str, status: str, notes: str | None = None) -> dict:
    """Move a reseller lead through watching/contacted/offer/purchased/listed/sold/rejected."""
    return service.update_resale_lead_status(lead_id, status, notes)


@mcp.tool()
def create_inventory_item(item: dict) -> dict:
    """Create a purchased inventory item for resale tracking."""
    return service.create_inventory_item(item)


@mcp.tool()
def mark_inventory_listed(inventory_id: str, listing_url: str, asking_price: float) -> dict:
    """Mark an inventory item as listed for sale."""
    return service.mark_inventory_listed(inventory_id, listing_url, asking_price)


@mcp.tool()
def mark_inventory_sold(
    inventory_id: str,
    sale_price: float,
    sold_url: str | None = None,
    outbound_shipping: float = 0.0,
    platform_fee_percent: float = 13.25,
) -> dict:
    """Mark inventory sold and calculate realized profit."""
    return service.mark_inventory_sold(
        inventory_id,
        sale_price,
        sold_url=sold_url,
        outbound_shipping=outbound_shipping,
        platform_fee_percent=platform_fee_percent,
    )


@mcp.tool()
def calculate_business_metrics() -> dict:
    """Summarize leads, inventory, revenue, realized profit, and ROI."""
    return service.calculate_business_metrics()


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
