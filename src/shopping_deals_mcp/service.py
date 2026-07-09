"""Search orchestration for the shopping deals MCP tools."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from shopping_deals_mcp.config import settings
from shopping_deals_mcp.models import Listing, PriceComparison, SearchResponse, SourceStatus
from shopping_deals_mcp.pricing import (
    dedupe_listings,
    effective_price,
    is_accessory_mismatch,
    is_model_token_mismatch,
    product_key,
    score_deals,
    title_similarity,
)
from shopping_deals_mcp.resale import (
    DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT,
    DEFAULT_PACKING_COST,
    ProfitInputs,
    ResaleStore,
    build_resale_comps,
    calculate_resale_profit,
    draft_ebay_listing,
    score_opportunity,
)
from shopping_deals_mcp.sources import build_sources
from shopping_deals_mcp.vehicle import (
    VehicleProfitInputs,
    build_vehicle_market_comps,
    calculate_vehicle_flip_profit,
    decode_vin,
    draft_ebay_motors_listing,
    florida_dealer_threshold_status,
    score_vehicle_opportunity,
    score_vehicle_title_risk,
)


class ShoppingDealsService:
    def __init__(self):
        self.sources = build_sources()
        self.resale_store = ResaleStore()

    def source_statuses(self) -> list[SourceStatus]:
        return [source.status() for source in self.sources.values()]

    async def search_products(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        max_results_per_source: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> SearchResponse:
        selected = sources or list(self.sources.keys())
        limit = max_results_per_source or settings.max_results_per_source
        tasks = {}
        source_errors: dict[str, str] = {}

        for source_name in selected:
            source = self.sources.get(source_name)
            if source is None:
                source_errors[source_name] = "Unknown source."
                continue
            status = source.status()
            if not status.available:
                source_errors[source_name] = (
                    "Source is not configured. Requires: " + ", ".join(status.requires)
                )
                continue
            tasks[source_name] = asyncio.create_task(
                source.search(
                    query,
                    max_results=limit,
                    price_min=price_min,
                    price_max=price_max,
                    condition=condition,
                    location=location,
                )
            )

        all_listings = []
        for source_name, task in tasks.items():
            try:
                all_listings.extend(await task)
            except Exception as exc:  # Keep partial results useful.
                source_errors[source_name] = f"{type(exc).__name__}: {exc}"

        listings = dedupe_listings(all_listings)
        listings.sort(
            key=lambda item: (
                is_accessory_mismatch(query, item.title),
                is_model_token_mismatch(query, item.title),
                -title_similarity(query, item.title),
                effective_price(item) is None,
                effective_price(item) or float("inf"),
                item.title,
            )
        )
        return SearchResponse(
            query=query,
            sources_requested=selected,
            sources_used=[name for name in tasks if name not in source_errors],
            source_errors=source_errors,
            total_results=len(listings),
            listings=listings,
        )

    async def find_best_deals(
        self,
        query: str,
        *,
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
        response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        listings = apply_tax_estimates(response.listings, tax_rate_percent, tax_on_shipping)
        scored = score_deals(query, listings)[:max_results]
        return {
            "query": query,
            "searched_at": response.searched_at,
            "source_errors": response.source_errors,
            "tax_rate_percent": resolved_tax_rate(tax_rate_percent),
            "tax_on_shipping": resolved_tax_on_shipping(tax_on_shipping),
            "total_results": response.total_results,
            "best_deals": [deal.model_dump() for deal in scored],
        }

    async def find_cheapest_offers(
        self,
        query: str,
        *,
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
        response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        listings = apply_tax_estimates(response.listings, tax_rate_percent, tax_on_shipping)
        eligible = [
            listing
            for listing in listings
            if effective_price(listing) is not None
            and not is_accessory_mismatch(query, listing.title)
            and not is_model_token_mismatch(query, listing.title)
        ]
        cheapest = sorted(
            eligible,
            key=lambda listing: (effective_price(listing) or float("inf"), listing.title),
        )
        return {
            "query": query,
            "searched_at": response.searched_at,
            "source_errors": response.source_errors,
            "tax_rate_percent": resolved_tax_rate(tax_rate_percent),
            "tax_on_shipping": resolved_tax_on_shipping(tax_on_shipping),
            "total_results": response.total_results,
            "eligible_results": len(eligible),
            "cheapest_offers": [listing.model_dump() for listing in cheapest[:max_results]],
        }

    async def compare_prices(
        self,
        query: str,
        *,
        sources: list[str] | None = None,
        max_results_per_source: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
        location: str | None = None,
    ) -> dict:
        response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        groups = defaultdict(list)
        for listing in response.listings:
            groups[product_key(listing.title) or listing.title.lower()].append(listing)

        comparisons: list[PriceComparison] = []
        for key, listings in groups.items():
            prices = [effective_price(listing) for listing in listings if effective_price(listing) is not None]
            comparisons.append(
                PriceComparison(
                    group_key=key,
                    title=listings[0].title,
                    count=len(listings),
                    low_price=min(prices) if prices else None,
                    high_price=max(prices) if prices else None,
                    average_price=(sum(prices) / len(prices)) if prices else None,
                    sources=sorted({listing.source for listing in listings}),
                    listings=listings,
                )
            )

        comparisons.sort(
            key=lambda item: (
                item.low_price is None,
                item.low_price if item.low_price is not None else float("inf"),
                -item.count,
            )
        )
        return {
            "query": query,
            "searched_at": response.searched_at,
            "source_errors": response.source_errors,
            "comparisons": [comparison.model_dump() for comparison in comparisons],
        }

    async def compare_area_prices(
        self,
        query: str,
        *,
        areas: list[str] | None = None,
        sources: list[str] | None = None,
        max_results_per_area: int | None = None,
        price_min: float | None = None,
        price_max: float | None = None,
        condition: str = "any",
    ) -> dict:
        selected_areas = areas or [
            "Miami Beach, FL",
            "Miami, FL",
            "Fort Lauderdale, FL",
            "New York, NY",
            "Los Angeles, CA",
        ]
        selected_sources = sources or ["offerup", "facebook_marketplace", "craigslist"]
        area_results = []
        for area in selected_areas:
            response = await self.search_products(
                query,
                sources=selected_sources,
                max_results_per_source=max_results_per_area,
                price_min=price_min,
                price_max=price_max,
                condition=condition,
                location=area,
            )
            priced = [
                effective_price(listing)
                for listing in response.listings
                if effective_price(listing) is not None
            ]
            prices = [price for price in priced if price is not None]
            area_results.append(
                {
                    "area": area,
                    "searched_at": response.searched_at,
                    "source_errors": response.source_errors,
                    "total_results": response.total_results,
                    "priced_results": len(prices),
                    "low_price": min(prices) if prices else None,
                    "median_price": _median(prices),
                    "high_price": max(prices) if prices else None,
                    "average_price": round(sum(prices) / len(prices), 2) if prices else None,
                    "sources_used": response.sources_used,
                    "listings": [listing.model_dump() for listing in response.listings],
                }
            )
        area_results.sort(
            key=lambda item: (
                item["median_price"] is None,
                item["median_price"] if item["median_price"] is not None else float("inf"),
                item["area"],
            )
        )
        return {
            "query": query,
            "areas": selected_areas,
            "sources": selected_sources,
            "area_results": area_results,
        }

    async def get_listing_details(self, source: str, listing_id: str) -> dict:
        source_client = self.sources.get(source)
        if source_client is None:
            return {"error": f"Unknown source: {source}"}
        status = source_client.status()
        if not status.available:
            return {"error": "Source is not configured.", "requires": status.requires}
        listing = await source_client.details(listing_id)
        if listing is None:
            return {"error": "Listing details are unavailable for this source or listing."}
        return listing.model_dump()

    async def get_ebay_sold_comps(
        self,
        query: str,
        *,
        max_results: int = 20,
        condition: str = "any",
    ) -> dict:
        response = await self.search_products(
            query,
            sources=["ebay"],
            max_results_per_source=max(max_results, 25),
            condition=condition,
        )
        comps = build_resale_comps(query, response.listings, max_comps=max_results)
        comps.update(
            {
                "searched_at": response.searched_at,
                "source_errors": response.source_errors,
            }
        )
        return comps

    def calculate_resale_profit(
        self,
        *,
        purchase_price: float,
        expected_sale_price: float,
        inbound_shipping: float = 0.0,
        outbound_shipping: float = 0.0,
        purchase_tax_rate_percent: float | None = None,
        platform_fee_percent: float = DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT,
        promoted_listing_percent: float = 0.0,
        payment_fixed_fee: float = 0.40,
        packing_cost: float = DEFAULT_PACKING_COST,
        misc_cost: float = 0.0,
        buyer_shipping_charged: float = 0.0,
    ) -> dict:
        tax_rate = purchase_tax_rate_percent
        if tax_rate is None:
            tax_rate = settings.estimated_tax_rate_percent or 0.0
        return calculate_resale_profit(
            ProfitInputs(
                purchase_price=purchase_price,
                expected_sale_price=expected_sale_price,
                inbound_shipping=inbound_shipping,
                outbound_shipping=outbound_shipping,
                purchase_tax_rate_percent=tax_rate,
                platform_fee_percent=platform_fee_percent,
                promoted_listing_percent=promoted_listing_percent,
                payment_fixed_fee=payment_fixed_fee,
                packing_cost=packing_cost,
                misc_cost=misc_cost,
                buyer_shipping_charged=buyer_shipping_charged,
            )
        )

    async def find_arbitrage_opportunities(
        self,
        query: str,
        *,
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
        platform_fee_percent: float = DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT,
        promoted_listing_percent: float = 0.0,
        packing_cost: float = DEFAULT_PACKING_COST,
    ) -> dict:
        comps = await self.get_ebay_sold_comps(query, max_results=30, condition=condition)
        expected_sale_price = comps.get("recommended_resale_price")
        if expected_sale_price is None:
            return {
                "query": query,
                "error": "Could not estimate resale value from eBay comps.",
                "comps": comps,
                "opportunities": [],
            }

        sources = buy_sources or ["facebook_marketplace", "craigslist", "offerup", "ebay"]
        buy_response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_max=price_max,
            condition=condition,
            location=location,
        )
        tax_rate = purchase_tax_rate_percent
        if tax_rate is None:
            tax_rate = settings.estimated_tax_rate_percent or 0.0
        opportunities = []
        for listing in buy_response.listings:
            purchase_price = effective_price(listing)
            if purchase_price is None:
                continue
            inbound_shipping = listing.shipping_cost or 0.0
            profit = calculate_resale_profit(
                ProfitInputs(
                    purchase_price=purchase_price,
                    expected_sale_price=float(expected_sale_price),
                    inbound_shipping=inbound_shipping,
                    outbound_shipping=outbound_shipping,
                    purchase_tax_rate_percent=tax_rate,
                    platform_fee_percent=platform_fee_percent,
                    promoted_listing_percent=promoted_listing_percent,
                    packing_cost=packing_cost,
                )
            )
            opportunity = score_opportunity(
                query,
                listing,
                profit,
                comp_count=int(comps.get("comp_count") or 0),
                min_profit=min_profit,
                min_roi_percent=min_roi_percent,
            )
            if profit["net_profit"] >= min_profit and profit["roi_percent"] >= min_roi_percent:
                opportunities.append(opportunity)

        opportunities.sort(
            key=lambda item: (
                -item["opportunity_score"],
                -item["net_profit"],
                item["risk_score"],
            )
        )
        return {
            "query": query,
            "searched_at": buy_response.searched_at,
            "buy_sources": sources,
            "sell_side": "ebay",
            "source_errors": buy_response.source_errors,
            "resale_comps": comps,
            "filters": {
                "min_profit": min_profit,
                "min_roi_percent": min_roi_percent,
                "price_max": price_max,
            },
            "opportunities": opportunities[:max_results],
        }

    def draft_ebay_listing(
        self,
        *,
        product_title: str,
        condition: str = "used",
        known_defects: str | None = None,
        included_accessories: str | None = None,
        comp_summary: dict | None = None,
    ) -> dict:
        return draft_ebay_listing(
            product_title=product_title,
            condition=condition,
            known_defects=known_defects,
            included_accessories=included_accessories,
            comp_summary=comp_summary,
        )

    def save_resale_lead(self, payload: dict) -> dict:
        return self.resale_store.save_lead(payload)

    def update_resale_lead_status(self, lead_id: str, status: str, notes: str | None = None) -> dict:
        return self.resale_store.update_lead_status(lead_id, status, notes)

    def create_inventory_item(self, payload: dict) -> dict:
        return self.resale_store.create_inventory_item(payload)

    def mark_inventory_listed(self, inventory_id: str, listing_url: str, asking_price: float) -> dict:
        return self.resale_store.mark_listed(inventory_id, listing_url, asking_price)

    def mark_inventory_sold(
        self,
        inventory_id: str,
        sale_price: float,
        *,
        sold_url: str | None = None,
        outbound_shipping: float = 0.0,
        platform_fee_percent: float = DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT,
    ) -> dict:
        return self.resale_store.mark_sold(
            inventory_id,
            sale_price,
            sold_url=sold_url,
            outbound_shipping=outbound_shipping,
            platform_fee_percent=platform_fee_percent,
        )

    def calculate_business_metrics(self) -> dict:
        return self.resale_store.metrics()

    def decode_vin(self, vin: str) -> dict:
        return decode_vin(vin)

    def calculate_vehicle_flip_profit(
        self,
        *,
        purchase_price: float,
        expected_sale_price: float,
        repair_cost: float = 0.0,
        transport_cost: float = 0.0,
        inspection_cost: float = 150.0,
        detail_cost: float = 150.0,
        title_registration_cost: float = 450.0,
        sales_tax_rate_percent: float = 0.0,
        storage_cost: float = 0.0,
        insurance_cost: float = 0.0,
        ebay_listing_fee: float | None = None,
        deposit_amount: float = 0.0,
        misc_cost: float = 0.0,
    ) -> dict:
        return calculate_vehicle_flip_profit(
            VehicleProfitInputs(
                purchase_price=purchase_price,
                expected_sale_price=expected_sale_price,
                repair_cost=repair_cost,
                transport_cost=transport_cost,
                inspection_cost=inspection_cost,
                detail_cost=detail_cost,
                title_registration_cost=title_registration_cost,
                sales_tax_rate_percent=sales_tax_rate_percent,
                storage_cost=storage_cost,
                insurance_cost=insurance_cost,
                ebay_listing_fee=ebay_listing_fee,
                deposit_amount=deposit_amount,
                misc_cost=misc_cost,
            )
        )

    def score_vehicle_title_risk(
        self,
        *,
        title_status: str = "unknown",
        has_title_in_hand: bool | None = None,
        vin: str | None = None,
        odometer_discrepancy: bool = False,
        seller_name_matches_title: bool | None = None,
        flood_risk_area: bool = True,
        lien_reported: bool = False,
    ) -> dict:
        return score_vehicle_title_risk(
            title_status=title_status,
            has_title_in_hand=has_title_in_hand,
            vin=vin,
            odometer_discrepancy=odometer_discrepancy,
            seller_name_matches_title=seller_name_matches_title,
            flood_risk_area=flood_risk_area,
            lien_reported=lien_reported,
        )

    def florida_dealer_threshold_status(
        self,
        *,
        vehicles_sold_or_offered_12mo: int,
        planned_new_vehicle_offers: int = 1,
    ) -> dict:
        return florida_dealer_threshold_status(
            vehicles_sold_or_offered_12mo=vehicles_sold_or_offered_12mo,
            planned_new_vehicle_offers=planned_new_vehicle_offers,
        )

    async def find_vehicle_arbitrage_opportunities(
        self,
        query: str,
        *,
        buy_sources: list[str] | None = None,
        location: str | None = None,
        max_results: int = 10,
        max_results_per_source: int | None = None,
        price_max: float | None = None,
        min_profit: float = 2_000.0,
        min_roi_percent: float = 20.0,
        repair_cost: float = 0.0,
        transport_cost: float = 500.0,
        inspection_cost: float = 150.0,
        detail_cost: float = 150.0,
        title_registration_cost: float = 450.0,
        sales_tax_rate_percent: float = 0.0,
        storage_cost: float = 0.0,
        insurance_cost: float = 0.0,
        vehicles_sold_or_offered_12mo: int = 0,
        title_status: str = "unknown",
        has_title_in_hand: bool | None = None,
    ) -> dict:
        comp_response = await self.search_products(
            query,
            sources=["ebay"],
            max_results_per_source=50,
        )
        comps = build_vehicle_market_comps(query, comp_response.listings, max_comps=20)
        expected_sale_price = comps.get("recommended_resale_price")
        if expected_sale_price is None:
            return {
                "query": query,
                "error": "Could not estimate vehicle resale value from eBay Motors active comps.",
                "market_comps": comps,
                "opportunities": [],
            }

        sources = buy_sources or ["facebook_marketplace", "craigslist", "offerup"]
        buy_response = await self.search_products(
            query,
            sources=sources,
            max_results_per_source=max_results_per_source,
            price_max=price_max,
            location=location,
        )
        title_risk = score_vehicle_title_risk(
            title_status=title_status,
            has_title_in_hand=has_title_in_hand,
            flood_risk_area=True,
        )
        dealer_threshold = florida_dealer_threshold_status(
            vehicles_sold_or_offered_12mo=vehicles_sold_or_offered_12mo,
            planned_new_vehicle_offers=1,
        )
        opportunities = []
        for listing in buy_response.listings:
            purchase_price = effective_price(listing)
            if purchase_price is None:
                continue
            profit = calculate_vehicle_flip_profit(
                VehicleProfitInputs(
                    purchase_price=purchase_price,
                    expected_sale_price=float(expected_sale_price),
                    repair_cost=repair_cost,
                    transport_cost=transport_cost,
                    inspection_cost=inspection_cost,
                    detail_cost=detail_cost,
                    title_registration_cost=title_registration_cost,
                    sales_tax_rate_percent=sales_tax_rate_percent,
                    storage_cost=storage_cost,
                    insurance_cost=insurance_cost,
                )
            )
            opportunity = score_vehicle_opportunity(
                query,
                listing,
                profit,
                comp_count=int(comps.get("comp_count") or 0),
                min_profit=min_profit,
                min_roi_percent=min_roi_percent,
                title_risk=title_risk,
                dealer_threshold=dealer_threshold,
            )
            if profit["net_profit"] >= min_profit and profit["roi_percent"] >= min_roi_percent:
                opportunities.append(opportunity)

        opportunities.sort(
            key=lambda item: (
                -item["opportunity_score"],
                -item["net_profit"],
                item["risk_score"],
            )
        )
        return {
            "query": query,
            "searched_at": buy_response.searched_at,
            "buy_sources": sources,
            "sell_side": "ebay_motors",
            "source_errors": buy_response.source_errors,
            "market_comps": comps,
            "assumptions": {
                "repair_cost": repair_cost,
                "transport_cost": transport_cost,
                "inspection_cost": inspection_cost,
                "detail_cost": detail_cost,
                "title_registration_cost": title_registration_cost,
                "sales_tax_rate_percent": sales_tax_rate_percent,
                "storage_cost": storage_cost,
                "insurance_cost": insurance_cost,
                "title_status": title_status,
                "has_title_in_hand": has_title_in_hand,
            },
            "filters": {
                "min_profit": min_profit,
                "min_roi_percent": min_roi_percent,
                "price_max": price_max,
            },
            "dealer_threshold": dealer_threshold,
            "opportunities": opportunities[:max_results],
        }

    def draft_ebay_motors_listing(
        self,
        *,
        year: int | None = None,
        make: str = "",
        model: str = "",
        trim: str = "",
        mileage: int | None = None,
        title_status: str = "clean",
        known_issues: str | None = None,
        recent_service: str | None = None,
    ) -> dict:
        return draft_ebay_motors_listing(
            year=year,
            make=make,
            model=model,
            trim=trim,
            mileage=mileage,
            title_status=title_status,
            known_issues=known_issues,
            recent_service=recent_service,
        )

    def save_vehicle_lead(self, vehicle: dict) -> dict:
        return self.resale_store.save_vehicle_lead(vehicle)

    def update_vehicle_status(self, vehicle_id: str, status: str, notes: str | None = None) -> dict:
        return self.resale_store.update_vehicle_status(vehicle_id, status, notes)


def resolved_tax_rate(tax_rate_percent: float | None) -> float | None:
    return tax_rate_percent if tax_rate_percent is not None else settings.estimated_tax_rate_percent


def resolved_tax_on_shipping(tax_on_shipping: bool | None) -> bool:
    return tax_on_shipping if tax_on_shipping is not None else settings.tax_shipping_by_default


def apply_tax_estimates(
    listings: list[Listing],
    tax_rate_percent: float | None = None,
    tax_on_shipping: bool | None = None,
) -> list[Listing]:
    rate = resolved_tax_rate(tax_rate_percent)
    if rate is None:
        return listings
    include_shipping = resolved_tax_on_shipping(tax_on_shipping)
    estimated: list[Listing] = []
    for listing in listings:
        base_total = listing.total_price if listing.total_price is not None else listing.price
        if base_total is None or listing.price is None:
            estimated.append(listing)
            continue
        taxable_base = base_total if include_shipping else listing.price
        tax = round(taxable_base * (rate / 100), 2)
        estimated.append(
            listing.model_copy(
                update={
                    "estimated_tax": tax,
                    "total_with_tax": round(base_total + tax, 2),
                }
            )
        )
    return estimated


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return round(sorted_values[midpoint], 2)
    return round((sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2, 2)
