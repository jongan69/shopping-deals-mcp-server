"""Vehicle flip research helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from shopping_deals_mcp.models import Listing
from shopping_deals_mcp.pricing import title_similarity
from shopping_deals_mcp.resale import build_resale_comps

EBAY_MOTORS_LOW_LISTING_FEE = 34.0
EBAY_MOTORS_HIGH_LISTING_FEE = 79.0
EBAY_MOTORS_HIGH_PRICE_THRESHOLD = 15_000.0
FLORIDA_DEALER_PRESUMPTION_THRESHOLD = 3
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
VIN_TRANSLITERATION = {
    **{str(number): number for number in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
MODEL_YEAR_CODES = {
    **dict(zip("123456789", range(2001, 2010), strict=True)),
    **dict(zip("ABCDEFGHJKLMNPRSTVWXY", range(2010, 2031), strict=True)),
}
WMI_COUNTRIES = {
    "1": "United States",
    "2": "Canada",
    "3": "Mexico",
    "4": "United States",
    "5": "United States",
    "J": "Japan",
    "K": "South Korea",
    "S": "United Kingdom",
    "W": "Germany",
    "Y": "Sweden/Finland",
    "Z": "Italy",
}


@dataclass(frozen=True)
class VehicleProfitInputs:
    purchase_price: float
    expected_sale_price: float
    repair_cost: float = 0.0
    transport_cost: float = 0.0
    inspection_cost: float = 150.0
    detail_cost: float = 150.0
    title_registration_cost: float = 450.0
    sales_tax_rate_percent: float = 0.0
    storage_cost: float = 0.0
    insurance_cost: float = 0.0
    ebay_listing_fee: float | None = None
    deposit_amount: float = 0.0
    deposit_processing_fee_percent: float = 2.8
    misc_cost: float = 0.0


def decode_vin(vin: str) -> dict[str, Any]:
    normalized = vin.strip().upper()
    valid_format = bool(VIN_RE.fullmatch(normalized))
    check_digit_expected = _vin_check_digit(normalized) if valid_format else None
    check_digit_actual = normalized[8] if valid_format else None
    country = WMI_COUNTRIES.get(normalized[0]) if valid_format else None
    return {
        "vin": normalized,
        "valid_format": valid_format,
        "check_digit_valid": (
            check_digit_expected == check_digit_actual if check_digit_expected is not None else None
        ),
        "check_digit_expected": check_digit_expected,
        "check_digit_actual": check_digit_actual,
        "wmi": normalized[:3] if valid_format else None,
        "country": country,
        "model_year_code": normalized[9] if valid_format else None,
        "model_year_estimate": MODEL_YEAR_CODES.get(normalized[9]) if valid_format else None,
        "plant_code": normalized[10] if valid_format else None,
        "serial": normalized[11:] if valid_format else None,
        "limitations": [
            "Offline VIN decoding only validates format/check digit and estimates year/country.",
            "Use an authoritative VIN/history provider for make, model, trim, title, accident, lien, and odometer data.",
        ],
    }


def calculate_vehicle_flip_profit(inputs: VehicleProfitInputs) -> dict[str, float]:
    listing_fee = inputs.ebay_listing_fee
    if listing_fee is None:
        listing_fee = ebay_motors_listing_fee(inputs.expected_sale_price)
    sales_tax = round(inputs.purchase_price * (inputs.sales_tax_rate_percent / 100), 2)
    deposit_processing_fee = round(
        inputs.deposit_amount * (inputs.deposit_processing_fee_percent / 100),
        2,
    )
    total_cost = round(
        inputs.purchase_price
        + sales_tax
        + inputs.repair_cost
        + inputs.transport_cost
        + inputs.inspection_cost
        + inputs.detail_cost
        + inputs.title_registration_cost
        + inputs.storage_cost
        + inputs.insurance_cost
        + listing_fee
        + deposit_processing_fee
        + inputs.misc_cost,
        2,
    )
    net_profit = round(inputs.expected_sale_price - total_cost, 2)
    cash_required = round(
        inputs.purchase_price
        + sales_tax
        + inputs.repair_cost
        + inputs.transport_cost
        + inputs.inspection_cost
        + inputs.detail_cost
        + inputs.title_registration_cost
        + inputs.storage_cost
        + inputs.insurance_cost
        + inputs.misc_cost,
        2,
    )
    roi_percent = round((net_profit / cash_required) * 100, 2) if cash_required else 0.0
    break_even_sale_price = round(total_cost, 2)
    max_buy_price_for_20_roi = max_vehicle_buy_price_for_target(
        expected_sale_price=inputs.expected_sale_price,
        target_roi_percent=20.0,
        repair_cost=inputs.repair_cost,
        transport_cost=inputs.transport_cost,
        inspection_cost=inputs.inspection_cost,
        detail_cost=inputs.detail_cost,
        title_registration_cost=inputs.title_registration_cost,
        sales_tax_rate_percent=inputs.sales_tax_rate_percent,
        storage_cost=inputs.storage_cost,
        insurance_cost=inputs.insurance_cost,
        listing_fee=listing_fee,
        deposit_processing_fee=deposit_processing_fee,
        misc_cost=inputs.misc_cost,
    )
    return {
        "purchase_price": round(inputs.purchase_price, 2),
        "expected_sale_price": round(inputs.expected_sale_price, 2),
        "sales_tax": sales_tax,
        "repair_cost": round(inputs.repair_cost, 2),
        "transport_cost": round(inputs.transport_cost, 2),
        "inspection_cost": round(inputs.inspection_cost, 2),
        "detail_cost": round(inputs.detail_cost, 2),
        "title_registration_cost": round(inputs.title_registration_cost, 2),
        "storage_cost": round(inputs.storage_cost, 2),
        "insurance_cost": round(inputs.insurance_cost, 2),
        "ebay_motors_listing_fee": round(listing_fee, 2),
        "deposit_processing_fee": deposit_processing_fee,
        "total_cost": total_cost,
        "net_profit": net_profit,
        "roi_percent": roi_percent,
        "break_even_sale_price": break_even_sale_price,
        "max_buy_price_for_20_roi": max_buy_price_for_20_roi,
    }


def ebay_motors_listing_fee(expected_sale_price: float) -> float:
    if expected_sale_price > EBAY_MOTORS_HIGH_PRICE_THRESHOLD:
        return EBAY_MOTORS_HIGH_LISTING_FEE
    return EBAY_MOTORS_LOW_LISTING_FEE


def max_vehicle_buy_price_for_target(
    *,
    expected_sale_price: float,
    target_roi_percent: float,
    repair_cost: float = 0.0,
    transport_cost: float = 0.0,
    inspection_cost: float = 150.0,
    detail_cost: float = 150.0,
    title_registration_cost: float = 450.0,
    sales_tax_rate_percent: float = 0.0,
    storage_cost: float = 0.0,
    insurance_cost: float = 0.0,
    listing_fee: float | None = None,
    deposit_processing_fee: float = 0.0,
    misc_cost: float = 0.0,
) -> float:
    if listing_fee is None:
        listing_fee = ebay_motors_listing_fee(expected_sale_price)
    target_roi = target_roi_percent / 100
    tax_rate = sales_tax_rate_percent / 100
    fixed_costs = (
        repair_cost
        + transport_cost
        + inspection_cost
        + detail_cost
        + title_registration_cost
        + storage_cost
        + insurance_cost
        + listing_fee
        + deposit_processing_fee
        + misc_cost
    )
    denominator = 1 + tax_rate + target_roi
    return round(max((expected_sale_price - fixed_costs) / denominator, 0.0), 2)


def score_vehicle_title_risk(
    *,
    title_status: str = "unknown",
    has_title_in_hand: bool | None = None,
    vin: str | None = None,
    odometer_discrepancy: bool = False,
    seller_name_matches_title: bool | None = None,
    flood_risk_area: bool = True,
    lien_reported: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    blockers: list[str] = []
    score = 20

    normalized_status = title_status.strip().lower()
    if normalized_status in {"salvage", "rebuilt", "flood", "parts", "certificate_of_destruction"}:
        score += 35
        warnings.append("Non-clean title status; resale market and buyer financing may be limited.")
    elif normalized_status in {"unknown", ""}:
        score += 25
        warnings.append("Title status is unknown.")

    if has_title_in_hand is False:
        score += 35
        blockers.append("Seller does not have title in hand.")
    elif has_title_in_hand is None:
        score += 15
        warnings.append("Title-in-hand status is unknown.")

    if seller_name_matches_title is False:
        score += 30
        blockers.append("Seller name does not match title.")
    elif seller_name_matches_title is None:
        score += 10
        warnings.append("Seller/title name match is unknown.")

    if vin:
        decoded = decode_vin(vin)
        if not decoded["valid_format"] or decoded["check_digit_valid"] is False:
            score += 30
            blockers.append("VIN failed basic validation.")
    else:
        score += 15
        warnings.append("VIN is missing.")

    if odometer_discrepancy:
        score += 35
        blockers.append("Odometer discrepancy reported.")
    if lien_reported:
        score += 35
        blockers.append("Lien reported; payoff/release must be verified before purchase.")
    if flood_risk_area:
        score += 10
        warnings.append("Flood-risk market; inspect for water intrusion and title branding.")

    score = min(score, 100)
    return {
        "risk_score": score,
        "risk_level": _risk_level(score),
        "blockers": blockers,
        "warnings": warnings,
        "required_checks": [
            "Confirm physical title is present before payment.",
            "Confirm VIN on dash, door jamb, and title match.",
            "Run vehicle history report.",
            "Check for liens, salvage/rebuilt/flood branding, and odometer anomalies.",
            "Use pre-purchase inspection or mobile mechanic before committing.",
        ],
    }


def florida_dealer_threshold_status(
    *,
    vehicles_sold_or_offered_12mo: int,
    planned_new_vehicle_offers: int = 1,
) -> dict[str, Any]:
    projected = vehicles_sold_or_offered_12mo + planned_new_vehicle_offers
    remaining_before_presumption = max(
        FLORIDA_DEALER_PRESUMPTION_THRESHOLD - vehicles_sold_or_offered_12mo,
        0,
    )
    return {
        "jurisdiction": "Florida",
        "vehicles_sold_or_offered_12mo": vehicles_sold_or_offered_12mo,
        "planned_new_vehicle_offers": planned_new_vehicle_offers,
        "projected_12mo_count": projected,
        "dealer_presumption_threshold": FLORIDA_DEALER_PRESUMPTION_THRESHOLD,
        "remaining_before_threshold": remaining_before_presumption,
        "likely_dealer_activity_presumption": projected >= FLORIDA_DEALER_PRESUMPTION_THRESHOLD,
        "note": (
            "Florida law creates a prima facie presumption of dealer activity at three or more "
            "motor vehicles bought, sold, dealt, offered, or displayed for sale in 12 months."
        ),
    }


def build_vehicle_market_comps(query: str, listings: list[Listing], *, max_comps: int = 20) -> dict[str, Any]:
    comps = build_resale_comps(query, listings, max_comps=max_comps)
    comps["basis"] = "active_ebay_motors_listing_proxy"
    comps["limitation"] = (
        "Uses active eBay listing data as a market proxy. Confirm sold/auction results, "
        "trim, mileage, title status, accident history, and location before buying."
    )
    return comps


def score_vehicle_opportunity(
    query: str,
    listing: Listing,
    profit: dict[str, float],
    *,
    comp_count: int,
    min_profit: float,
    min_roi_percent: float,
    title_risk: dict[str, Any],
    dealer_threshold: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    blockers = list(title_risk.get("blockers") or [])
    relevance = title_similarity(query, listing.title)
    if comp_count < 4:
        warnings.append("Thin vehicle comp set; resale estimate is weak.")
    if profit["net_profit"] < min_profit:
        warnings.append("Below requested minimum net profit.")
    if profit["roi_percent"] < min_roi_percent:
        warnings.append("Below requested minimum ROI.")
    if relevance < 0.45:
        warnings.append("Weak title match; verify year/make/model/trim manually.")
    if dealer_threshold.get("likely_dealer_activity_presumption"):
        warnings.append("Projected Florida activity may trigger dealer-license presumption.")
    if listing.source in {"facebook_marketplace", "craigslist", "offerup"}:
        warnings.append("Private/local seller; verify title, VIN, liens, and seller identity.")

    risk_score = min(
        100,
        int(title_risk["risk_score"])
        + (20 if comp_count < 4 else 0)
        + (10 if relevance < 0.45 else 0),
    )
    opportunity_score = (
        min(max(profit["roi_percent"], 0), 100) * 0.35
        + min(max(profit["net_profit"], 0), 5_000) / 5_000 * 45
        + max(0, 20 - risk_score * 0.2)
    )
    if blockers:
        opportunity_score = min(opportunity_score, 35)

    return {
        "listing": listing.model_dump(),
        "net_profit": profit["net_profit"],
        "roi_percent": profit["roi_percent"],
        "max_buy_price_for_20_roi": profit["max_buy_price_for_20_roi"],
        "opportunity_score": round(opportunity_score, 2),
        "risk_score": risk_score,
        "risk_level": _risk_level(risk_score),
        "warnings": warnings + list(title_risk.get("warnings") or []),
        "blockers": blockers,
        "dealer_threshold": dealer_threshold,
    }


def draft_ebay_motors_listing(
    *,
    year: int | None = None,
    make: str = "",
    model: str = "",
    trim: str = "",
    mileage: int | None = None,
    title_status: str = "clean",
    known_issues: str | None = None,
    recent_service: str | None = None,
) -> dict[str, Any]:
    title_parts = [str(year) if year else "", make, model, trim]
    title = " ".join(part.strip() for part in title_parts if part and part.strip())
    details = [
        f"Title status: {title_status}.",
        f"Mileage: {mileage:,}." if mileage is not None else "Mileage: verify from odometer photo.",
        "VIN should be provided to serious buyers after screening.",
    ]
    if recent_service:
        details.append(f"Recent service: {recent_service}.")
    if known_issues:
        details.append(f"Known issues: {known_issues}.")
    else:
        details.append("Known issues: none disclosed; buyer inspection welcome.")
    return {
        "title": title[:80],
        "format": "fixed_price_or_auction_with_reserve",
        "description": "\n".join(details),
        "photo_checklist": [
            "Exterior all four corners",
            "Interior front/rear seats",
            "Dashboard with mileage visible",
            "VIN plate and door jamb sticker",
            "Engine bay",
            "Tires and wheels",
            "Undercarriage/rust areas",
            "Any damage, warning lights, leaks, or wear",
            "Title with sensitive info covered",
        ],
        "required_disclosures": [
            "Title brand/status",
            "Known mechanical issues",
            "Accident/flood history if known",
            "Odometer accuracy",
            "Lien/payoff status",
            "Pickup/payment terms",
        ],
        "fee_note": "eBay Motors vehicle listings use listing-package fees rather than normal item final value fees.",
    }


def _vin_check_digit(vin: str) -> str | None:
    if not VIN_RE.fullmatch(vin):
        return None
    total = sum(VIN_TRANSLITERATION[char] * weight for char, weight in zip(vin, VIN_WEIGHTS, strict=True))
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def _risk_level(score: int) -> str:
    if score >= 80:
        return "very_high"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"
