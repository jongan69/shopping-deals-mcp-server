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
        return [
            Listing(
                id="fake-1",
                source=self.name,
                marketplace="Fake",
                title=f"{query} bargain",
                url="https://example.com/fake-1",
                price=99,
                shipping_cost=10,
                total_price=109,
                condition="new",
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
