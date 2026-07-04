from shopping_deals_mcp.sources.offerup import _parse_offerup_html


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
