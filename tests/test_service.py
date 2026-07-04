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
