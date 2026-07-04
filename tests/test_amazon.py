from shopping_deals_mcp.sources.amazon import _clean_title


def test_clean_amazon_sponsored_title_prefix():
    raw = (
        "Sponsored Sponsored You’re seeing this ad based on the product’s relevance "
        "to your search query. Leave ad feedback DJI Osmo Pocket 4 Standard Combo"
    )

    assert _clean_title(raw) == "DJI Osmo Pocket 4 Standard Combo"
