from shopping_deals_mcp.models import Listing
from shopping_deals_mcp.pricing import (
    dedupe_listings,
    is_accessory_mismatch,
    is_model_token_mismatch,
    parse_price,
    product_key,
    score_deals,
)


def test_parse_price_handles_common_formats():
    assert parse_price("$1,299.99") == 1299.99
    assert parse_price("Free shipping") is None
    assert parse_price(42) == 42.0


def test_product_key_removes_noise_words():
    assert product_key("New Sony WH-1000XM5 Wireless Headphones") == "sony wh 1000xm5 wireless headphones"


def test_score_deals_prefers_relevant_low_price():
    listings = [
        Listing(
            id="1",
            source="ebay",
            marketplace="eBay",
            title="Sony WH-1000XM5 wireless headphones black",
            url="https://example.com/1",
            price=199.0,
            condition="used",
        ),
        Listing(
            id="2",
            source="ebay",
            marketplace="eBay",
            title="Sony WH-1000XM5 wireless headphones black",
            url="https://example.com/2",
            price=299.0,
            condition="used",
        ),
    ]

    scored = score_deals("Sony WH-1000XM5 headphones", listings)

    assert scored[0].listing.id == "1"
    assert scored[0].deal_score > scored[1].deal_score


def test_score_deals_penalizes_accessory_mismatch():
    listings = [
        Listing(
            id="1",
            source="ebay",
            marketplace="eBay",
            title="USB charging cable for Sony WH-1000XM5 headphones",
            url="https://example.com/1",
            price=5.0,
            condition="new",
        ),
        Listing(
            id="2",
            source="ebay",
            marketplace="eBay",
            title="Sony WH-1000XM5 wireless noise canceling headphones",
            url="https://example.com/2",
            price=199.0,
            condition="used",
        ),
    ]

    scored = score_deals("Sony WH-1000XM5 headphones", listings)

    assert is_accessory_mismatch("Sony WH-1000XM5 headphones", listings[0].title)
    assert scored[0].listing.id == "2"


def test_score_deals_penalizes_compatible_accessory_with_exact_model_token():
    listings = [
        Listing(
            id="1",
            source="amazon",
            marketplace="Amazon",
            title="Split Filter Kit for DJI Osmo Pocket 4P",
            url="https://example.com/1",
            price=45.99,
            condition="new",
        ),
        Listing(
            id="2",
            source="ebay",
            marketplace="eBay",
            title="DJI Osmo Pocket 4P Standard Combo Action Camera Handheld Gimbal",
            url="https://example.com/2",
            price=829.0,
            condition="new",
        ),
    ]

    scored = score_deals("DJI OSMO Pocket 4P", listings)

    assert is_accessory_mismatch("DJI OSMO Pocket 4P", listings[0].title)
    assert scored[0].listing.id == "2"


def test_accessories_plural_counts_as_accessory_mismatch():
    assert is_accessory_mismatch(
        "DJI OSMO Pocket 4P",
        "Genuine Osmo Pocket 4P(Pro) Vlog Combo Accessories",
    )


def test_screen_film_and_sunshade_count_as_accessories():
    assert is_accessory_mismatch(
        "DJI OSMO Pocket 4P",
        "2PCS Sunnylife Tempered Glass Film For DJI Osmo Pocket 4P/4/3 Remote Viewfinder",
    )
    assert is_accessory_mismatch(
        "DJI OSMO Pocket 4P",
        "For DJI Osmo Pocket 4P/4/3 Camera Quick Release Folding Sunshade Sun Hood Shield",
    )


def test_score_uses_comparable_price_baseline_not_accessory_baseline():
    listings = [
        Listing(
            id="accessory",
            source="ebay",
            marketplace="eBay",
            title="2PCS Tempered Glass Film For DJI Osmo Pocket 4P",
            url="https://example.com/accessory",
            price=9.98,
            condition="new",
        ),
        Listing(
            id="cheap-camera",
            source="ebay",
            marketplace="eBay",
            title="DJI Osmo Pocket Four Pro(4P) Standard Combo/Vlog Creator Combo",
            url="https://example.com/cheap-camera",
            price=759.0,
            condition="new",
        ),
        Listing(
            id="expensive-camera",
            source="ebay",
            marketplace="eBay",
            title="DJI Osmo Pocket 4P Standard Combo Action Camera Handheld Gimbal",
            url="https://example.com/expensive-camera",
            price=829.0,
            condition="new",
        ),
    ]

    scored = score_deals("DJI OSMO Pocket 4P", listings)

    assert scored[0].listing.id == "cheap-camera"
    assert scored[-1].listing.id == "accessory"


def test_dedupe_keeps_cheapest_same_title():
    listings = [
        Listing(
            id="1",
            source="ebay",
            marketplace="eBay",
            title="DJI Osmo Pocket 4P Standard Combo",
            url="https://example.com/itm/1",
            price=829.0,
            condition="new",
        ),
        Listing(
            id="2",
            source="ebay",
            marketplace="eBay",
            title="DJI Osmo Pocket 4P Standard Combo",
            url="https://example.com/itm/2",
            price=759.0,
            condition="new",
        ),
    ]

    deduped = dedupe_listings(listings)

    assert len(deduped) == 1
    assert deduped[0].id == "2"


def test_score_deals_penalizes_model_variant_mismatch():
    listings = [
        Listing(
            id="1",
            source="offerup",
            marketplace="OfferUp",
            title="DJI OSMO POCKET 4 - CREATOR COMBO",
            url="https://example.com/1",
            price=949.0,
            condition="used",
        ),
        Listing(
            id="2",
            source="ebay",
            marketplace="eBay",
            title="DJI OSMO Pocket 4P Creator Combo",
            url="https://example.com/2",
            price=1299.0,
            condition="new",
        ),
    ]

    scored = score_deals("DJI OSMO Pocket 4P", listings)

    assert is_model_token_mismatch("DJI OSMO Pocket 4P", listings[0].title)
    assert not is_model_token_mismatch("DJI OSMO Pocket 4P", listings[1].title)
    assert scored[0].listing.id == "2"
