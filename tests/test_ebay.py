from shopping_deals_mcp.sources.ebay import _query_variants


def test_ebay_query_variants_expand_4p_aliases():
    variants = _query_variants("DJI OSMO Pocket 4P")

    assert "DJI Osmo Pocket Four Pro" in variants
    assert "DJI Osmo Pocket 4P Standard Combo" in variants
    assert "DJI Osmo Pocket 4P Vlog Combo" in variants
