from shopping_deals_mcp.resale import ResaleStore
from shopping_deals_mcp.vehicle import (
    VehicleProfitInputs,
    calculate_vehicle_flip_profit,
    decode_vin,
    florida_dealer_threshold_status,
    score_vehicle_title_risk,
)


def test_decode_vin_validates_check_digit():
    decoded = decode_vin("1HGCM82633A004352")

    assert decoded["valid_format"] is True
    assert decoded["check_digit_valid"] is True
    assert decoded["country"] == "United States"
    assert decoded["model_year_estimate"] == 2003


def test_calculate_vehicle_flip_profit_uses_ebay_motors_listing_fee():
    result = calculate_vehicle_flip_profit(
        VehicleProfitInputs(
            purchase_price=7000,
            expected_sale_price=10500,
            repair_cost=500,
            transport_cost=400,
            inspection_cost=150,
            detail_cost=150,
            title_registration_cost=450,
        )
    )

    assert result["ebay_motors_listing_fee"] == 34
    assert result["net_profit"] == 1816
    assert result["roi_percent"] > 20
    assert result["max_buy_price_for_20_roi"] > 7000


def test_calculate_vehicle_flip_profit_uses_high_listing_fee_above_threshold():
    result = calculate_vehicle_flip_profit(
        VehicleProfitInputs(purchase_price=12000, expected_sale_price=18000)
    )

    assert result["ebay_motors_listing_fee"] == 79


def test_florida_threshold_flags_third_vehicle_offer():
    status = florida_dealer_threshold_status(
        vehicles_sold_or_offered_12mo=2,
        planned_new_vehicle_offers=1,
    )

    assert status["likely_dealer_activity_presumption"] is True
    assert status["projected_12mo_count"] == 3


def test_score_vehicle_title_risk_flags_blockers():
    risk = score_vehicle_title_risk(
        title_status="unknown",
        has_title_in_hand=False,
        vin="BADVIN",
        seller_name_matches_title=False,
        lien_reported=True,
    )

    assert risk["risk_level"] == "very_high"
    assert len(risk["blockers"]) >= 3


def test_resale_store_tracks_vehicle_leads(tmp_path):
    store = ResaleStore(tmp_path / "resale.json")

    lead = store.save_vehicle_lead({"title": "2008 Honda Fit", "status": "researching"})
    updated = store.update_vehicle_status(lead["id"], "inspection_needed", "Ask for VIN.")
    metrics = store.metrics()

    assert updated["status"] == "inspection_needed"
    assert metrics["vehicle_lead_count"] == 1
    assert metrics["vehicle_leads_by_status"]["inspection_needed"] == 1
