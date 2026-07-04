from shopping_deals_mcp.sources.facebook_marketplace import (
    _extract_lsd_token,
    _parse_facebook_marketplace_results,
    _resolve_coordinates,
)


def test_extract_lsd_token_from_public_page_script():
    html = '<script>require("LSD",[],{"token":"abc123_TOKEN"},0);</script>'

    assert _extract_lsd_token(html) == "abc123_TOKEN"


def test_resolve_coordinates_from_location_string():
    assert _resolve_coordinates("40.7128,-74.0060", config=object()) == (40.7128, -74.006)


def test_resolve_coordinates_from_known_city():
    assert _resolve_coordinates("New Orleans", config=object()) == (29.9511, -90.0715)


def test_parse_facebook_marketplace_results():
    data = {
        "data": {
            "marketplace_search": {
                "feed_units": {
                    "edges": [
                        {
                            "node": {
                                "__typename": "MarketplaceFeedListingStoryObject",
                                "listing": {
                                    "id": "12345",
                                    "marketplace_listing_title": "DJI Osmo Pocket Camera",
                                    "listing_price": {
                                        "amount": "19900",
                                        "formatted_amount": "$199",
                                    },
                                    "primary_listing_photo": {
                                        "image": {"uri": "https://example.com/image.jpg"}
                                    },
                                    "location": {
                                        "reverse_geocode": {
                                            "city_page": {"display_name": "Brooklyn, NY"}
                                        }
                                    },
                                    "is_shipping_offered": True,
                                },
                            }
                        }
                    ]
                }
            }
        }
    }

    listings = _parse_facebook_marketplace_results(data, max_results=10)

    assert len(listings) == 1
    assert listings[0].source == "facebook_marketplace"
    assert listings[0].marketplace == "Facebook Marketplace"
    assert listings[0].price == 199
    assert listings[0].shipping == "Shipping offered"
    assert listings[0].location == "Brooklyn, NY"
