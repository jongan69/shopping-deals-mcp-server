import pytest

from shopping_deals_mcp.models import Listing, SourceStatus
from shopping_deals_mcp.service import ShoppingDealsService
from shopping_deals_mcp.sources.base import MarketplaceSource


class FakeSource(MarketplaceSource):
    name = "fake"
    display_name = "Fake"

    def status(self):
        return SourceStatus(name=self.name, display_name=self.display_name, available=True)

    async def search(self, query, *, max_results, price_min=None, price_max=None, condition="any", location=None):
        price = 149 if location == "New York, NY" else 99
        title_suffix = f" {location}" if location else ""
        return [
            Listing(
                id="fake-1",
                source=self.name,
                marketplace="Fake",
                title=f"{query} bargain{title_suffix}",
                url=f"https://example.com/{location or 'default'}",
                price=price,
                shipping_cost=10,
                total_price=price + 10,
                condition="new",
                location=location,
            )
        ]


@pytest.mark.asyncio
async def test_service_search_uses_selected_sources():
    service = ShoppingDealsService()
    service.sources = {"fake": FakeSource()}

    response = await service.search_products("camera", sources=["fake"], max_results_per_source=5)

    assert response.total_results == 1
    assert response.sources_used == ["fake"]
    assert response.listings[0].title == "camera bargain"


@pytest.mark.asyncio
async def test_find_cheapest_offers_can_apply_tax_estimate():
    service = ShoppingDealsService()
    service.sources = {"fake": FakeSource()}

    result = await service.find_cheapest_offers(
        "camera",
        sources=["fake"],
        max_results_per_source=5,
        tax_rate_percent=10,
        tax_on_shipping=True,
    )

    offer = result["cheapest_offers"][0]
    assert offer["estimated_tax"] == 10.9
    assert offer["total_with_tax"] == 119.9
    assert result["tax_rate_percent"] == 10
    assert result["tax_on_shipping"] is True


@pytest.mark.asyncio
async def test_compare_area_prices_runs_each_area():
    service = ShoppingDealsService()
    service.sources = {"fake": FakeSource()}

    result = await service.compare_area_prices(
        "camera",
        sources=["fake"],
        areas=["Miami Beach, FL", "New York, NY"],
        max_results_per_area=5,
    )

    assert [area["area"] for area in result["area_results"]] == [
        "Miami Beach, FL",
        "New York, NY",
    ]
    assert result["area_results"][0]["median_price"] == 109
    assert result["area_results"][1]["median_price"] == 159
