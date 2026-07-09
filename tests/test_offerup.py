from shopping_deals_mcp.config import Settings
from shopping_deals_mcp.sources.offerup import _parse_offerup_html, _resolve_offerup_location


def test_parse_offerup_next_data_listings():
    html = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
      {
        "props": {
          "pageProps": {
            "searchFeedResponse": {
              "tiles": [
                {
                  "__typename": "ModularFeedListing",
                  "listingId": "abc-123",
                  "title": "DJI OSMO POCKET 4 - CREATOR COMBO",
                  "price": "949",
                  "locationName": "Sunny Isles Beach, FL",
                  "image": {"url": "https://example.com/image.jpg"}
                }
              ]
            }
          }
        }
      }
      </script>
    </body></html>
    """

    listings = _parse_offerup_html(html, 10)

    assert len(listings) == 1
    assert listings[0].source == "offerup"
    assert listings[0].price == 949.0
    assert listings[0].url == "https://offerup.com/item/detail/abc-123"


def test_offerup_default_location_is_miami_beach():
    location = _resolve_offerup_location(None, Settings())

    assert location["city"] == "Miami Beach"
    assert location["state"] == "FL"
    assert location["zipCode"] == "33139"


def test_offerup_location_override_supports_other_markets():
    location = _resolve_offerup_location("New York, NY", Settings())

    assert location["city"] == "New York"
    assert location["state"] == "NY"
    assert location["zipCode"] == "10001"
