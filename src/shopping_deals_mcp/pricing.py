"""Price parsing and deal scoring helpers."""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from statistics import mean

from shopping_deals_mcp.models import DealResult, Listing

PRICE_RE = re.compile(r"\$?\s*([0-9]+(?:\.[0-9]{2})?)")
STOP_WORDS = {
    "the",
    "a",
    "an",
    "for",
    "with",
    "and",
    "or",
    "new",
    "used",
    "open",
    "box",
}
MODEL_TOKEN_RE = re.compile(r"(?=.*\d)[a-z0-9]{2,}")
ACCESSORY_TERMS = {
    "adapter",
    "cable",
    "case",
    "charger",
    "charging",
    "clip",
    "connector",
    "cord",
    "cover",
    "earpad",
    "earpads",
    "filter",
    "filters",
    "film",
    "films",
    "glass",
    "grip",
    "handle",
    "hinge",
    "kit",
    "kits",
    "kickstand",
    "lens",
    "magnetic",
    "mount",
    "pads",
    "part",
    "parts",
    "protector",
    "repair",
    "replacement",
    "shade",
    "shield",
    "skin",
    "sleeve",
    "stand",
    "strap",
    "sunshade",
    "tripod",
    "viewfinder",
    "accessory",
    "accessories",
}


def parse_price(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value) if value >= 0 else None

    text = str(value).replace(",", "")
    match = PRICE_RE.search(text)
    if not match:
        return None

    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def product_key(title: str) -> str:
    tokens = [
        token
        for token in normalize_text(title).split()
        if token not in STOP_WORDS and len(token) > 1
    ]
    return " ".join(tokens[:8])


def title_similarity(query: str, title: str) -> float:
    query_norm = normalize_text(query)
    title_norm = normalize_text(title)
    if not query_norm or not title_norm:
        return 0.0

    query_tokens = set(query_norm.split())
    title_tokens = set(title_norm.split())
    token_overlap = len(query_tokens & title_tokens) / max(len(query_tokens), 1)
    fuzzy = SequenceMatcher(None, query_norm, title_norm).ratio()
    return max(token_overlap, fuzzy * 0.8)


def dedupe_listings(listings: list[Listing]) -> list[Listing]:
    seen_urls: set[str] = set()
    by_title_key: dict[tuple[str, str], Listing] = {}

    for listing in listings:
        url_key = listing.url.split("?")[0].rstrip("/").lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        title_key = (listing.source, normalize_text(listing.title))
        existing = by_title_key.get(title_key)
        if existing is None:
            by_title_key[title_key] = listing
            continue

        if _price_sort_value(listing) < _price_sort_value(existing):
            by_title_key[title_key] = listing

    return list(by_title_key.values())


def _price_sort_value(listing: Listing) -> float:
    price = effective_price(listing)
    return price if price is not None else float("inf")


def score_deals(query: str, listings: list[Listing]) -> list[DealResult]:
    comparable_priced = [
        effective_price(listing)
        for listing in listings
        if effective_price(listing) is not None
        and not is_accessory_mismatch(query, listing.title)
        and not is_model_token_mismatch(query, listing.title)
    ]
    priced = comparable_priced or [
        effective_price(listing) for listing in listings if effective_price(listing) is not None
    ]
    if priced:
        low = min(priced)
        high = max(priced)
        avg = mean(priced)
    else:
        low = high = avg = None

    scored: list[DealResult] = []
    for listing in listings:
        relevance = title_similarity(query, listing.title)
        listing_price = effective_price(listing)
        price_score = 35.0

        warnings: list[str] = []
        if listing_price is None:
            price_score = 15.0
            warnings.append("No price was available, so the deal score is less certain.")
        elif low is not None and high is not None and not math.isclose(low, high):
            price_score = 55.0 * (1 - ((listing_price - low) / (high - low)))
        elif avg:
            price_score = 45.0

        source_bonus = {
            "ebay": 10.0,
            "serpapi_google_shopping": 8.0,
            "craigslist": 4.0,
            "amazon": 6.0,
        }.get(listing.source, 3.0)

        condition_bonus = 0.0
        condition = listing.condition.lower()
        if condition in {"new", "open_box", "refurbished"}:
            condition_bonus = 8.0
        elif condition == "used":
            condition_bonus = 4.0

        shipping_bonus = 0.0
        if listing.shipping:
            shipping_text = listing.shipping.lower()
            if "free" in shipping_text:
                shipping_bonus = 5.0
            elif "pickup" in shipping_text:
                shipping_bonus = 2.0

        accessory_mismatch = is_accessory_mismatch(query, listing.title)
        accessory_penalty = 70.0 if accessory_mismatch else 0.0
        if accessory_mismatch:
            warnings.append("Looks like an accessory, repair part, or replacement component.")
        model_mismatch = is_model_token_mismatch(query, listing.title)
        model_penalty = 65.0 if model_mismatch else 0.0
        if model_mismatch:
            warnings.append("Missing an exact model/variant token from the query.")

        score = max(
            0.0,
            min(
                100.0,
                price_score
                + (relevance * 22.0)
                + source_bonus
                + condition_bonus
                + shipping_bonus
                - accessory_penalty
                - model_penalty,
            ),
        )

        if relevance < 0.35:
            warnings.append("Title match is weak; verify this is the exact product.")
        if listing.source == "craigslist":
            warnings.append("Local marketplace listing; verify seller identity and availability.")
        if accessory_mismatch:
            score = min(score, 30.0)
        if model_mismatch:
            score = min(score, 35.0)

        rank_reason = _rank_reason(listing, low, avg, relevance)
        scored.append(
            DealResult(
                listing=listing,
                deal_score=round(score, 2),
                rank_reason=rank_reason,
                warnings=warnings,
            )
        )

    scored.sort(key=lambda result: result.deal_score, reverse=True)
    return scored


def effective_price(listing: Listing) -> float | None:
    return listing.total_price if listing.total_price is not None else listing.price


def _rank_reason(listing: Listing, low: float | None, avg: float | None, relevance: float) -> str:
    pieces: list[str] = []
    price = effective_price(listing)
    basis = "shipped total" if listing.total_price is not None else "price"
    if price is not None and low is not None and math.isclose(price, low):
        pieces.append(f"lowest observed {basis}")
    elif price is not None and avg is not None and price < avg:
        pieces.append(f"below the observed average {basis} of ${avg:.2f}")
    elif price is not None:
        pieces.append(f"{basis} within the observed result range")
    else:
        pieces.append("price unavailable")

    if relevance >= 0.75:
        pieces.append("strong title match")
    elif relevance >= 0.45:
        pieces.append("reasonable title match")
    else:
        pieces.append("weak title match")

    if listing.condition and listing.condition != "unknown":
        pieces.append(f"condition: {listing.condition}")

    return "; ".join(pieces)


def is_accessory_mismatch(query: str, title: str) -> bool:
    query_tokens = set(normalize_text(query).split())
    title_tokens = set(normalize_text(title).split())
    accessory_hits = title_tokens & ACCESSORY_TERMS
    title_text = normalize_text(title)
    compatible_language = "compatible with" in title_text or "for " in title_text
    return bool(accessory_hits and (compatible_language or not accessory_hits <= query_tokens))


def is_model_token_mismatch(query: str, title: str) -> bool:
    query_iphone_model = _phone_model_number(query, "iphone")
    title_iphone_model = _phone_model_number(title, "iphone")
    if query_iphone_model and title_iphone_model and query_iphone_model != title_iphone_model:
        return True

    query_tokens = set(normalize_text(query).split())
    title_tokens = set(normalize_text(title).split())
    required_model_tokens = {token for token in query_tokens if MODEL_TOKEN_RE.fullmatch(token)}
    return bool(required_model_tokens - title_tokens)


def _phone_model_number(text: str, family: str) -> str | None:
    match = re.search(rf"\b{re.escape(family)}\s+(\d{{1,2}})\b", normalize_text(text))
    return match.group(1) if match else None
