from shopping_deals_mcp.models import Listing
from shopping_deals_mcp.resale import (
    ProfitInputs,
    ResaleStore,
    build_resale_comps,
    calculate_resale_profit,
    draft_ebay_listing,
    score_opportunity,
)


def test_calculate_resale_profit_includes_tax_fees_and_shipping():
    result = calculate_resale_profit(
        ProfitInputs(
            purchase_price=100,
            expected_sale_price=180,
            inbound_shipping=10,
            outbound_shipping=12,
            purchase_tax_rate_percent=8,
            platform_fee_percent=13,
            payment_fixed_fee=0.40,
            packing_cost=2,
        )
    )

    assert result["purchase_tax"] == 8.8
    assert result["platform_fee"] == 23.4
    assert result["net_profit"] == 23.4
    assert result["roi_percent"] > 19
    assert result["break_even_sale_price"] == 153.11


def test_build_resale_comps_filters_accessories_and_reports_active_proxy():
    listings = [
        Listing(
            id="camera",
            source="ebay",
            marketplace="eBay",
            title="Sony a6700 mirrorless camera body",
            url="https://example.com/camera",
            price=899,
            condition="used",
        ),
        Listing(
            id="case",
            source="ebay",
            marketplace="eBay",
            title="Case for Sony a6700 mirrorless camera",
            url="https://example.com/case",
            price=19,
            condition="new",
        ),
    ]

    comps = build_resale_comps("Sony a6700 camera", listings)

    assert comps["basis"] == "active_ebay_listing_proxy"
    assert comps["comp_count"] == 1
    assert comps["recommended_resale_price"] == 899
    assert comps["comps"][0]["id"] == "camera"


def test_score_opportunity_flags_local_marketplace_risk():
    listing = Listing(
        id="lead",
        source="facebook_marketplace",
        marketplace="Facebook Marketplace",
        title="Sony a6700 mirrorless camera body",
        url="https://example.com/lead",
        price=500,
        condition="used",
    )
    profit = calculate_resale_profit(
        ProfitInputs(purchase_price=500, expected_sale_price=800, outbound_shipping=15)
    )

    scored = score_opportunity(
        "Sony a6700 camera",
        listing,
        profit,
        comp_count=8,
        min_profit=50,
        min_roi_percent=20,
    )

    assert scored["net_profit"] > 100
    assert scored["roi_percent"] > 20
    assert scored["risk_score"] >= 50
    assert any("Local marketplace risk" in warning for warning in scored["warnings"])


def test_resale_store_tracks_inventory_metrics(tmp_path):
    store = ResaleStore(tmp_path / "resale.json")

    lead = store.save_lead({"title": "Sony a6700", "source": "facebook_marketplace"})
    store.update_lead_status(lead["id"], "purchased", "Met seller and bought it.")
    item = store.create_inventory_item({"title": "Sony a6700", "purchase_price": 500})
    store.mark_listed(item["id"], "https://www.ebay.com/itm/123", 799)
    sold = store.mark_sold(item["id"], 775, outbound_shipping=18)
    metrics = store.metrics()

    assert sold["status"] == "sold"
    assert sold["profit"]["net_profit"] > 100
    assert metrics["lead_count"] == 1
    assert metrics["sold_count"] == 1
    assert metrics["realized_net_profit"] == sold["profit"]["net_profit"]


def test_draft_ebay_listing_keeps_title_under_80_chars():
    draft = draft_ebay_listing(
        product_title="Sony Alpha a6700 Mirrorless Camera Body Black With Battery Charger Strap",
        condition="used",
        included_accessories="battery, charger, strap",
    )

    assert len(draft["title"]) <= 80
    assert "battery, charger, strap" in draft["description"]
    assert draft["photo_checklist"]
