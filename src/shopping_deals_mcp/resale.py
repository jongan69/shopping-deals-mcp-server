"""Resale arbitrage calculations and business state helpers."""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from shopping_deals_mcp.config import settings
from shopping_deals_mcp.models import Listing
from shopping_deals_mcp.pricing import (
    effective_price,
    is_accessory_mismatch,
    is_model_token_mismatch,
    title_similarity,
)

DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT = 13.25
DEFAULT_PAYMENT_FIXED_FEE = 0.40
DEFAULT_PACKING_COST = 2.0

LEAD_STATUSES = {
    "watching",
    "contacted",
    "offer_made",
    "purchased",
    "listed",
    "sold",
    "rejected",
}


@dataclass(frozen=True)
class ProfitInputs:
    purchase_price: float
    expected_sale_price: float
    inbound_shipping: float = 0.0
    outbound_shipping: float = 0.0
    purchase_tax_rate_percent: float = 0.0
    platform_fee_percent: float = DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT
    promoted_listing_percent: float = 0.0
    payment_fixed_fee: float = DEFAULT_PAYMENT_FIXED_FEE
    packing_cost: float = DEFAULT_PACKING_COST
    misc_cost: float = 0.0
    buyer_shipping_charged: float = 0.0
    include_buyer_shipping_in_fee_basis: bool = True


def calculate_resale_profit(inputs: ProfitInputs) -> dict[str, float]:
    """Return deterministic resale profit math for an eBay-style sale."""
    purchase_tax = round(
        (inputs.purchase_price + inputs.inbound_shipping)
        * (inputs.purchase_tax_rate_percent / 100),
        2,
    )
    gross_revenue = inputs.expected_sale_price + inputs.buyer_shipping_charged
    fee_basis = inputs.expected_sale_price
    if inputs.include_buyer_shipping_in_fee_basis:
        fee_basis += inputs.buyer_shipping_charged
    platform_fee = round(fee_basis * (inputs.platform_fee_percent / 100), 2)
    promoted_fee = round(fee_basis * (inputs.promoted_listing_percent / 100), 2)
    total_cost = round(
        inputs.purchase_price
        + inputs.inbound_shipping
        + purchase_tax
        + inputs.outbound_shipping
        + inputs.packing_cost
        + inputs.misc_cost
        + platform_fee
        + promoted_fee
        + inputs.payment_fixed_fee,
        2,
    )
    net_profit = round(gross_revenue - total_cost, 2)
    cash_invested = round(
        inputs.purchase_price
        + inputs.inbound_shipping
        + purchase_tax
        + inputs.packing_cost
        + inputs.misc_cost,
        2,
    )
    roi_percent = round((net_profit / cash_invested) * 100, 2) if cash_invested else 0.0

    variable_sale_fee_rate = (
        inputs.platform_fee_percent
        + inputs.promoted_listing_percent
    ) / 100
    fixed_costs_before_sale = (
        inputs.purchase_price
        + inputs.inbound_shipping
        + purchase_tax
        + inputs.outbound_shipping
        + inputs.packing_cost
        + inputs.misc_cost
        + inputs.payment_fixed_fee
    )
    break_even_sale_price = _safe_round_up(
        fixed_costs_before_sale / max(1 - variable_sale_fee_rate, 0.01)
    )
    max_buy_price_for_20_roi = max_buy_price_for_target(
        expected_sale_price=inputs.expected_sale_price,
        target_roi_percent=20.0,
        inbound_shipping=inputs.inbound_shipping,
        outbound_shipping=inputs.outbound_shipping,
        purchase_tax_rate_percent=inputs.purchase_tax_rate_percent,
        platform_fee_percent=inputs.platform_fee_percent,
        promoted_listing_percent=inputs.promoted_listing_percent,
        payment_fixed_fee=inputs.payment_fixed_fee,
        packing_cost=inputs.packing_cost,
        misc_cost=inputs.misc_cost,
        buyer_shipping_charged=inputs.buyer_shipping_charged,
    )

    return {
        "purchase_price": round(inputs.purchase_price, 2),
        "expected_sale_price": round(inputs.expected_sale_price, 2),
        "gross_revenue": round(gross_revenue, 2),
        "purchase_tax": purchase_tax,
        "platform_fee": platform_fee,
        "promoted_listing_fee": promoted_fee,
        "payment_fixed_fee": round(inputs.payment_fixed_fee, 2),
        "packing_cost": round(inputs.packing_cost, 2),
        "total_cost": total_cost,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
        "break_even_sale_price": break_even_sale_price,
        "max_buy_price_for_20_roi": max_buy_price_for_20_roi,
    }


def max_buy_price_for_target(
    *,
    expected_sale_price: float,
    target_roi_percent: float,
    inbound_shipping: float = 0.0,
    outbound_shipping: float = 0.0,
    purchase_tax_rate_percent: float = 0.0,
    platform_fee_percent: float = DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT,
    promoted_listing_percent: float = 0.0,
    payment_fixed_fee: float = DEFAULT_PAYMENT_FIXED_FEE,
    packing_cost: float = DEFAULT_PACKING_COST,
    misc_cost: float = 0.0,
    buyer_shipping_charged: float = 0.0,
) -> float:
    tax_rate = purchase_tax_rate_percent / 100
    target_roi = target_roi_percent / 100
    fee_rate = (platform_fee_percent + promoted_listing_percent) / 100
    revenue = expected_sale_price + buyer_shipping_charged
    sale_fees = (expected_sale_price + buyer_shipping_charged) * fee_rate + payment_fixed_fee
    fixed_costs = inbound_shipping * (1 + tax_rate) + outbound_shipping + packing_cost + misc_cost + sale_fees
    denominator = 1 + tax_rate + target_roi
    return round(max((revenue - fixed_costs) / denominator, 0.0), 2)


def build_resale_comps(query: str, listings: list[Listing], *, max_comps: int = 20) -> dict[str, Any]:
    eligible = [
        listing
        for listing in listings
        if effective_price(listing) is not None
        and not is_accessory_mismatch(query, listing.title)
        and not is_model_token_mismatch(query, listing.title)
        and title_similarity(query, listing.title) >= 0.35
    ]
    eligible.sort(key=lambda listing: (effective_price(listing) or float("inf"), listing.title))
    prices = [effective_price(listing) for listing in eligible if effective_price(listing) is not None]
    prices = [price for price in prices if price is not None]
    return {
        "query": query,
        "basis": "active_ebay_listing_proxy",
        "limitation": (
            "Current implementation uses active eBay listings as resale comps. "
            "True sold-comps support requires a completed/sold-listing data source."
        ),
        "comp_count": len(prices),
        "low_price": min(prices) if prices else None,
        "median_price": round(median(prices), 2) if prices else None,
        "high_price": max(prices) if prices else None,
        "average_price": round(sum(prices) / len(prices), 2) if prices else None,
        "recommended_resale_price": recommended_resale_price(prices),
        "sell_through_confidence": sell_through_confidence(len(prices), prices),
        "comps": [listing.model_dump() for listing in eligible[:max_comps]],
    }


def recommended_resale_price(prices: list[float]) -> float | None:
    if not prices:
        return None
    sorted_prices = sorted(prices)
    if len(sorted_prices) >= 4:
        trimmed = sorted_prices[1:-1]
    else:
        trimmed = sorted_prices
    return round(median(trimmed), 2)


def sell_through_confidence(comp_count: int, prices: list[float]) -> str:
    if comp_count >= 15 and _coefficient_of_variation(prices) < 0.35:
        return "medium"
    if comp_count >= 6:
        return "low_medium"
    if comp_count > 0:
        return "low"
    return "unknown"


def score_opportunity(
    query: str,
    listing: Listing,
    profit: dict[str, float],
    *,
    comp_count: int,
    min_profit: float,
    min_roi_percent: float,
) -> dict[str, Any]:
    warnings: list[str] = []
    relevance = title_similarity(query, listing.title)
    if is_accessory_mismatch(query, listing.title):
        warnings.append("Looks like an accessory or part; reject unless that is intentional.")
    if is_model_token_mismatch(query, listing.title):
        warnings.append("Model token mismatch; verify exact variant before buying.")
    if listing.source in {"craigslist", "facebook_marketplace", "offerup"}:
        warnings.append("Local marketplace risk; verify seller identity, condition, and serial/authenticity.")
    if comp_count < 4:
        warnings.append("Thin comp set; resale estimate is weak.")
    if profit["net_profit"] < min_profit:
        warnings.append("Below requested minimum net profit.")
    if profit["roi_percent"] < min_roi_percent:
        warnings.append("Below requested minimum ROI.")

    risk_score = 25
    if listing.source in {"facebook_marketplace", "craigslist", "offerup"}:
        risk_score += 25
    if listing.condition in {"unknown", "used"}:
        risk_score += 10
    if relevance < 0.5:
        risk_score += 20
    if comp_count < 4:
        risk_score += 15
    risk_score = min(risk_score, 100)

    opportunity_score = (
        min(max(profit["roi_percent"], 0), 100) * 0.45
        + min(max(profit["net_profit"], 0), 250) / 250 * 35
        + max(0, 20 - risk_score * 0.2)
    )
    return {
        "listing": listing.model_dump(),
        "net_profit": profit["net_profit"],
        "roi_percent": profit["roi_percent"],
        "max_buy_price_for_20_roi": profit["max_buy_price_for_20_roi"],
        "opportunity_score": round(opportunity_score, 2),
        "risk_score": risk_score,
        "warnings": warnings,
    }


def draft_ebay_listing(
    *,
    product_title: str,
    condition: str = "used",
    known_defects: str | None = None,
    included_accessories: str | None = None,
    comp_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clean_title = _ebay_title(product_title)
    suggested_price = None
    if comp_summary:
        suggested_price = comp_summary.get("recommended_resale_price") or comp_summary.get("median_price")
    bullets = [
        f"Condition: {condition.replace('_', ' ')}.",
        "Tested and working unless otherwise noted.",
    ]
    if included_accessories:
        bullets.append(f"Includes: {included_accessories}.")
    if known_defects:
        bullets.append(f"Disclosure: {known_defects}.")
    else:
        bullets.append("No known defects observed during inspection.")
    return {
        "title": clean_title,
        "suggested_price": suggested_price,
        "format": "buy_it_now",
        "condition": condition,
        "description": "\n".join(bullets),
        "photo_checklist": [
            "Front, back, top, bottom, and ports",
            "Serial/model label if safe to show",
            "Screen/lens closeups",
            "Included accessories",
            "Any scratches, dents, missing parts, or defects",
        ],
        "shipping_recommendation": "Use calculated shipping for heavy items; use buyer-paid or padded flat-rate only when dimensions are known.",
        "disclosure_checklist": [
            "Confirm exact model number",
            "Confirm activation/account locks are removed where relevant",
            "Confirm battery health or runtime when relevant",
            "List missing accessories explicitly",
        ],
    }


class ResaleStore:
    """Small JSON store for local reselling workflow state."""

    def __init__(self, path: str | Path = settings.resale_store_path):
        self.path = Path(path).expanduser()

    def save_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        lead = {
            "id": payload.get("id") or f"lead_{uuid.uuid4().hex[:12]}",
            "status": payload.get("status") or "watching",
            "created_at": _now(),
            "updated_at": _now(),
            **payload,
        }
        lead["status"] = _valid_status(lead["status"])
        data["leads"][lead["id"]] = lead
        self._write(data)
        return lead

    def update_lead_status(self, lead_id: str, status: str, notes: str | None = None) -> dict[str, Any]:
        data = self._read()
        if lead_id not in data["leads"]:
            raise KeyError(f"Unknown lead: {lead_id}")
        lead = data["leads"][lead_id]
        lead["status"] = _valid_status(status)
        lead["updated_at"] = _now()
        if notes:
            lead.setdefault("notes", [])
            if isinstance(lead["notes"], list):
                lead["notes"].append({"at": _now(), "text": notes})
        self._write(data)
        return lead

    def create_inventory_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        item = {
            "id": payload.get("id") or f"inv_{uuid.uuid4().hex[:12]}",
            "status": payload.get("status") or "purchased",
            "created_at": _now(),
            "updated_at": _now(),
            **payload,
        }
        data["inventory"][item["id"]] = item
        self._write(data)
        return item

    def save_vehicle_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        lead = {
            "id": payload.get("id") or f"veh_{uuid.uuid4().hex[:12]}",
            "status": payload.get("status") or "researching",
            "created_at": _now(),
            "updated_at": _now(),
            **payload,
        }
        data["vehicles"][lead["id"]] = lead
        self._write(data)
        return lead

    def update_vehicle_status(
        self,
        vehicle_id: str,
        status: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        if vehicle_id not in data["vehicles"]:
            raise KeyError(f"Unknown vehicle lead: {vehicle_id}")
        lead = data["vehicles"][vehicle_id]
        lead["status"] = status
        lead["updated_at"] = _now()
        if notes:
            lead.setdefault("notes", [])
            if isinstance(lead["notes"], list):
                lead["notes"].append({"at": _now(), "text": notes})
        self._write(data)
        return lead

    def mark_listed(self, inventory_id: str, listing_url: str, asking_price: float) -> dict[str, Any]:
        data = self._read()
        if inventory_id not in data["inventory"]:
            raise KeyError(f"Unknown inventory item: {inventory_id}")
        item = data["inventory"][inventory_id]
        item.update(
            {
                "status": "listed",
                "listing_url": listing_url,
                "asking_price": asking_price,
                "listed_at": _now(),
                "updated_at": _now(),
            }
        )
        self._write(data)
        return item

    def mark_sold(
        self,
        inventory_id: str,
        sale_price: float,
        *,
        sold_url: str | None = None,
        outbound_shipping: float = 0.0,
        platform_fee_percent: float = DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT,
    ) -> dict[str, Any]:
        data = self._read()
        if inventory_id not in data["inventory"]:
            raise KeyError(f"Unknown inventory item: {inventory_id}")
        item = data["inventory"][inventory_id]
        purchase_price = float(item.get("purchase_price") or 0)
        inbound_shipping = float(item.get("inbound_shipping") or 0)
        tax_rate = float(item.get("purchase_tax_rate_percent") or 0)
        profit = calculate_resale_profit(
            ProfitInputs(
                purchase_price=purchase_price,
                expected_sale_price=sale_price,
                inbound_shipping=inbound_shipping,
                outbound_shipping=outbound_shipping,
                purchase_tax_rate_percent=tax_rate,
                platform_fee_percent=platform_fee_percent,
            )
        )
        item.update(
            {
                "status": "sold",
                "sale_price": sale_price,
                "sold_url": sold_url,
                "sold_at": _now(),
                "updated_at": _now(),
                "profit": profit,
            }
        )
        self._write(data)
        return item

    def metrics(self) -> dict[str, Any]:
        data = self._read()
        inventory = list(data["inventory"].values())
        sold = [item for item in inventory if item.get("status") == "sold"]
        active = [item for item in inventory if item.get("status") != "sold"]
        cash_invested = sum(float(item.get("purchase_price") or 0) for item in active)
        sold_revenue = sum(float(item.get("sale_price") or 0) for item in sold)
        net_profit = sum(float((item.get("profit") or {}).get("net_profit") or 0) for item in sold)
        return {
            "lead_count": len(data["leads"]),
            "vehicle_lead_count": len(data["vehicles"]),
            "inventory_count": len(inventory),
            "active_inventory_count": len(active),
            "sold_count": len(sold),
            "cash_invested_active": round(cash_invested, 2),
            "sold_revenue": round(sold_revenue, 2),
            "realized_net_profit": round(net_profit, 2),
            "average_realized_roi_percent": round(
                sum(float((item.get("profit") or {}).get("roi_percent") or 0) for item in sold)
                / len(sold),
                2,
            )
            if sold
            else 0.0,
            "leads_by_status": _count_by_status(data["leads"].values()),
            "vehicle_leads_by_status": _count_by_status(data["vehicles"].values()),
            "inventory_by_status": _count_by_status(inventory),
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"leads": {}, "inventory": {}, "vehicles": {}}
        data = json.loads(self.path.read_text())
        data.setdefault("leads", {})
        data.setdefault("inventory", {})
        data.setdefault("vehicles", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _coefficient_of_variation(prices: list[float]) -> float:
    if len(prices) < 2:
        return 1.0
    avg = sum(prices) / len(prices)
    if not avg:
        return 1.0
    variance = sum((price - avg) ** 2 for price in prices) / len(prices)
    return math.sqrt(variance) / avg


def _ebay_title(title: str) -> str:
    words = re.sub(r"\s+", " ", title).strip().split()
    candidate = " ".join(words)
    if len(candidate) <= 80:
        return candidate
    output: list[str] = []
    length = 0
    for word in words:
        next_length = length + len(word) + (1 if output else 0)
        if next_length > 80:
            break
        output.append(word)
        length = next_length
    return " ".join(output)


def _safe_round_up(value: float) -> float:
    return round(math.ceil(value * 100) / 100, 2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _valid_status(status: str) -> str:
    if status not in LEAD_STATUSES:
        raise ValueError(f"Status must be one of: {', '.join(sorted(LEAD_STATUSES))}")
    return status


def _count_by_status(items: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts
