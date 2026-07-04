# Shopping Deals MCP Server

Standalone MCP server for searching products, comparing prices, and ranking the best deals across shopping platforms.

It replaces the old FastAPI marketplace app shape with a focused MCP surface:

- `search_products` - searches enabled platforms and returns normalized listings.
- `find_best_deals` - searches, scores, and explains the strongest deals.
- `compare_prices` - groups comparable listings and reports price ranges.
- `get_listing_details` - fetches source-specific listing details where supported.
- `list_sources` - shows source availability and required configuration.

## Sources

| Source | Coverage | Requires |
| --- | --- | --- |
| Google Shopping via SerpApi | Broad retail coverage such as Amazon, Walmart, Target, eBay, merchant sites | `SERPAPI_API_KEY` |
| eBay Browse API | Official eBay item search and detail lookups | `EBAY_ACCESS_TOKEN` or `EBAY_APP_ID` + `EBAY_CERT_ID` |
| eBay public search | No-key eBay search fallback | none |
| Craigslist RSS | Local used marketplace listings | none, configure `CRAIGSLIST_SITES` |
| OfferUp public search | Local used marketplace listings | none |
| Amazon public search | Amazon product search HTML parser | `SHOPPING_ENABLE_AMAZON_SCRAPE=true`; may be blocked |

## Setup

```bash
cd /Users/jonathangan/LocalCode/shopping-deals-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` with any API keys you want to enable.

## Run

Stdio transport, for local MCP clients:

```bash
shopping-deals-mcp --transport stdio
```

Streamable HTTP transport, for inspector/testing:

```bash
shopping-deals-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Then connect an MCP client to:

```text
http://127.0.0.1:8000/mcp
```

## Cloudflare Worker

This repo also includes a TypeScript Worker implementation for remote MCP clients.

```bash
npm install
cp .env .dev.vars
npm run typecheck
npm run dev -- --port 8787
```

Set production Worker secrets before deploying:

```bash
printf '%s' "$EBAY_APP_ID" | npx wrangler secret put EBAY_APP_ID
printf '%s' "$EBAY_CERT_ID" | npx wrangler secret put EBAY_CERT_ID
printf '%s' "$EBAY_DEV_ID" | npx wrangler secret put EBAY_DEV_ID
npm run deploy
```

Current deployed MCP endpoint:

```text
https://shopping-deals-mcp.jonathang132298.workers.dev/mcp
```

Codex remote MCP registration:

```bash
codex mcp add shopping-deals-remote --url https://shopping-deals-mcp.jonathang132298.workers.dev/mcp
```

## Example Tool Calls

Find ranked deals:

```json
{
  "query": "sony wh-1000xm5 headphones",
  "max_results": 10,
  "price_max": 275,
  "condition": "any",
  "sources": ["serpapi_google_shopping", "ebay", "ebay_public", "craigslist"]
}
```

Compare prices:

```json
{
  "query": "macbook air m2 16gb",
  "location": "newyork",
  "max_results_per_source": 15
}
```

## Tests

```bash
pytest
```

## Notes

This server is deliberately key-aware. Official APIs and shopping aggregators are more reliable than scraping, so unavailable sources report a clear setup requirement instead of failing noisily. The deal score is not a guarantee of authenticity, availability, warranty, or seller safety; use it as a triage signal and verify the listing before buying.

Remote Worker verification on July 4, 2026 confirmed live MCP calls for eBay, Amazon, and OfferUp. Craigslist direct RSS returned HTTP 403 and the no-key Jina Reader fallback returned HTTP 429 from Cloudflare Worker egress, so Craigslist needs a paid/API-backed provider or a non-Worker fetch path before it can be considered fully remote-functional.
