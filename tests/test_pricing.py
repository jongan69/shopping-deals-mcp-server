from shopping_deals_mcp.models import Listing
from shopping_deals_mcp.pricing import parse_price, product_key, score_deals


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
