# Shopping Deals MCP Server

Shopping Deals MCP Server is a Model Context Protocol server for finding products, comparing marketplace listings, and ranking the cheapest real offers across eBay, Facebook Marketplace, Amazon, Craigslist, and OfferUp.

It is built for agents that need to answer questions like:

- "Find the cheapest DJI OSMO Pocket 4P shipped to me."
- "Compare exact-model prices across marketplaces."
- "Avoid accessory listings, wrong variants, and fake low prices with high shipping."
- "Estimate tax and sort by final landed cost."

## What It Does

- Searches multiple shopping sources from one MCP interface.
- Normalizes listings into a common schema.
- Separates item price, shipping cost, shipped total, estimated tax, and estimated final total.
- Penalizes accessories, parts, and wrong model variants.
- Handles edge cases like `Pocket 4P` vs `Pocket 4`.
- Can run locally over stdio or remotely as a Cloudflare Worker MCP endpoint.

## MCP Tools

| Tool | Purpose |
| --- | --- |
| `list_sources` | Show configured sources and setup requirements. |
| `search_products` | Return normalized listings across selected platforms. |
| `find_best_deals` | Rank strongest deals using price, relevance, condition, source, and warnings. |
| `find_cheapest_offers` | Filter exact-model offers and sort by shipped total plus estimated tax when supplied. |
| `compare_prices` | Group comparable listings and summarize observed price ranges. |
| `get_listing_details` | Fetch source-specific listing details where supported. |

## Sources

| Source | Coverage | Requires |
| --- | --- | --- |
| eBay Browse API | Official eBay item search, shipping, and detail lookups | `EBAY_ACCESS_TOKEN` or `EBAY_APP_ID` + `EBAY_CERT_ID` |
| Facebook Marketplace public search | Local used marketplace listings | `location` as `latitude,longitude` or `SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE/LONGITUDE`; experimental |
| Craigslist static search HTML | Local used marketplace listings | none, configure `CRAIGSLIST_SITES` |
| OfferUp public search | Local used marketplace listings | none |
| Amazon public search | Amazon product search HTML parser | `SHOPPING_ENABLE_AMAZON_SCRAPE=true`; may be blocked |
| Google Shopping via SerpApi | Broad retail coverage such as Amazon, Walmart, Target, eBay, merchant sites | `SERPAPI_API_KEY` |

Scraped/public sources can change or block automated traffic. Official APIs are more reliable.

## Requirements

- Python 3.10+
- Node.js 20+ for the Cloudflare Worker version
- eBay developer credentials for reliable eBay results
- Optional: SerpApi key for broad Google Shopping coverage
- Optional: Cloudflare account for remote hosting

## Use The Hosted MCP Server

You can use the public hosted MCP server without cloning this repo:

```text
https://shopping-deals-mcp.jonathang132298.workers.dev/mcp
```

Add it to Codex:

```bash
codex mcp add shopping-deals-remote --url https://shopping-deals-mcp.jonathang132298.workers.dev/mcp
codex mcp get shopping-deals-remote
```

Use it from any MCP client that supports Streamable HTTP:

```json
{
  "mcpServers": {
    "shopping-deals": {
      "url": "https://shopping-deals-mcp.jonathang132298.workers.dev/mcp"
    }
  }
}
```

Health and source status:

```text
https://shopping-deals-mcp.jonathang132298.workers.dev/health
```

The hosted Worker uses the maintainer's configured API keys and public marketplace parsers. If you want to use your own eBay, SerpApi, or Cloudflare account, follow the local setup or deployment steps below.

## Quick Start: Local MCP Server

```bash
git clone https://github.com/jongan69/shopping-deals-mcp-server.git
cd shopping-deals-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` with your own credentials:

```bash
EBAY_APP_ID=your-ebay-client-id
EBAY_CERT_ID=your-ebay-client-secret
EBAY_DEV_ID=your-ebay-dev-id
EBAY_MARKETPLACE_ID=EBAY_US
EBAY_USE_SANDBOX=false
SHOPPING_ENABLE_AMAZON_SCRAPE=true
SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE=40.7128
SHOPPING_FACEBOOK_MARKETPLACE_LONGITUDE=-74.0060
```

Run over stdio:

```bash
shopping-deals-mcp --transport stdio
```

Run over Streamable HTTP for local testing:

```bash
shopping-deals-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Local HTTP MCP endpoint:

```text
http://127.0.0.1:8000/mcp
```

## Add To Codex

Local stdio server:

```bash
codex mcp add shopping-deals -- /absolute/path/to/shopping-deals-mcp-server/.venv/bin/shopping-deals-mcp --transport stdio
```

Remote Streamable HTTP server:

```bash
codex mcp add shopping-deals-remote --url https://shopping-deals-mcp.jonathang132298.workers.dev/mcp
```

Verify:

```bash
codex mcp get shopping-deals-remote
```

## Add To Any MCP Client

Use the local stdio command:

```json
{
  "mcpServers": {
    "shopping-deals": {
      "command": "/absolute/path/to/shopping-deals-mcp-server/.venv/bin/shopping-deals-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

Or use a remote Streamable HTTP endpoint:

```text
https://shopping-deals-mcp.jonathang132298.workers.dev/mcp
```

## Cloudflare Worker Deployment

This repo includes a TypeScript Worker implementation for remote MCP clients.

Install dependencies:

```bash
npm install
cp .env .dev.vars
npm run typecheck
npm run dev -- --port 8787
```

Test locally:

```text
http://127.0.0.1:8787/health
http://127.0.0.1:8787/mcp
```

Before deploying, change the Worker name in `wrangler.jsonc` if `shopping-deals-mcp` is already taken in your Cloudflare account:

```json
{
  "name": "your-shopping-deals-mcp"
}
```

Upload secrets:

```bash
printf '%s' "$EBAY_APP_ID" | npx wrangler secret put EBAY_APP_ID
printf '%s' "$EBAY_CERT_ID" | npx wrangler secret put EBAY_CERT_ID
printf '%s' "$EBAY_DEV_ID" | npx wrangler secret put EBAY_DEV_ID
```

Deploy:

```bash
npm run deploy
```

Your remote MCP endpoint will be:

```text
https://your-worker.your-subdomain.workers.dev/mcp
```

## Optional Tax Estimates

eBay Browse search results do not return the buyer's final checkout tax amount. This server supports estimated tax when you provide a tax rate.

Set defaults:

```bash
SHOPPING_ESTIMATED_TAX_RATE_PERCENT=8.875
SHOPPING_TAX_SHIPPING=true
```

Or pass per tool call:

```json
{
  "query": "DJI OSMO Pocket 4P",
  "sources": ["ebay"],
  "max_results": 5,
  "max_results_per_source": 50,
  "tax_rate_percent": 8.875,
  "tax_on_shipping": true
}
```

Returned listings can include:

- `price`
- `shipping_cost`
- `total_price`
- `estimated_tax`
- `total_with_tax`

Use `find_cheapest_offers` when the goal is the lowest estimated final cost.

## Example Tool Calls

Find the cheapest exact-model offer by shipped total plus estimated tax:

```json
{
  "query": "DJI OSMO Pocket 4P",
  "sources": ["ebay"],
  "max_results": 10,
  "max_results_per_source": 50,
  "tax_rate_percent": 8.875,
  "tax_on_shipping": true
}
```

Find ranked deals across marketplaces:

```json
{
  "query": "sony wh-1000xm5 headphones",
  "sources": ["ebay", "facebook_marketplace", "craigslist", "offerup", "amazon"],
  "location": "40.7128,-74.0060",
  "max_results": 10,
  "max_results_per_source": 20,
  "condition": "any"
}
```

Search Facebook Marketplace near New York City:

```json
{
  "query": "used bike",
  "sources": ["facebook_marketplace"],
  "location": "40.7128,-74.0060",
  "max_results_per_source": 10
}
```

Compare prices:

```json
{
  "query": "macbook air m2 16gb",
  "sources": ["ebay", "craigslist", "offerup"],
  "location": "newyork",
  "max_results_per_source": 15
}
```

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `EBAY_ACCESS_TOKEN` | optional | Existing eBay OAuth access token. |
| `EBAY_APP_ID` | recommended | eBay client ID for OAuth client credentials. |
| `EBAY_CERT_ID` | recommended | eBay client secret for OAuth client credentials. |
| `EBAY_DEV_ID` | optional | eBay dev ID, stored for account completeness. |
| `EBAY_MARKETPLACE_ID` | optional | Defaults to `EBAY_US`. |
| `EBAY_USE_SANDBOX` | optional | Set `true` for sandbox eBay APIs. |
| `SERPAPI_API_KEY` | optional | Enables Google Shopping via SerpApi. |
| `CRAIGSLIST_SITES` | optional | Comma-separated Craigslist sites. |
| `SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE` | optional | Default Facebook Marketplace search latitude. |
| `SHOPPING_FACEBOOK_MARKETPLACE_LONGITUDE` | optional | Default Facebook Marketplace search longitude. |
| `SHOPPING_FACEBOOK_MARKETPLACE_RADIUS_KM` | optional | Facebook Marketplace search radius. Defaults to `16`. |
| `SHOPPING_ENABLE_AMAZON_SCRAPE` | optional | Enables Amazon public HTML parsing. |
| `SHOPPING_HTTP_TIMEOUT_SECONDS` | optional | Request timeout. Defaults to `15`. |
| `SHOPPING_MAX_RESULTS_PER_SOURCE` | optional | Default per-source search size. |
| `SHOPPING_ESTIMATED_TAX_RATE_PERCENT` | optional | Default tax estimate rate. |
| `SHOPPING_TAX_SHIPPING` | optional | Whether shipping is included in estimated tax base. Defaults to `true`. |

## Development

Python checks:

```bash
source .venv/bin/activate
pytest
ruff check .
```

Worker checks:

```bash
npm install
npm run typecheck
```

## License

MIT

## Notes And Limitations

- Deal scores are triage signals, not purchase guarantees.
- Always verify seller reputation, return policy, warranty, shipping, taxes, and authenticity before buying.
- Amazon, Craigslist, Facebook Marketplace, and OfferUp public parsers may break if those sites change markup or block traffic.
- Facebook Marketplace support is experimental. It uses Facebook's public Marketplace web feed with an anonymous page token and requires a local search center.
- Craigslist RSS returns HTTP 403 from Cloudflare Worker egress, so the Worker uses Craigslist static search HTML cards.
- Tax is estimated from a supplied rate. Final checkout tax may differ.
