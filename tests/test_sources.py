from shopping_deals_mcp.sources.craigslist import _parse_rss


def test_parse_craigslist_rss():
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title><![CDATA[Sony headphones - $120]]></title>
        <link>https://newyork.craigslist.org/mnh/ele/d/test/1234567890.html</link>
        <description><![CDATA[Great condition]]></description>
        <pubDate>Sat, 04 Jul 2026 12:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    listings = _parse_rss("newyork", rss, 10)

    assert len(listings) == 1
    assert listings[0].price == 120.0
    assert listings[0].source == "craigslist"
