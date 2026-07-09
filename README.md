# Shopping Deals MCP Server

Shopping Deals MCP Server is a Model Context Protocol server for finding products, comparing marketplace listings, and ranking the cheapest real offers across eBay, Facebook Marketplace, Amazon, Craigslist, and OfferUp.

It is built for agents that need to answer questions like:

- "Find the cheapest DJI OSMO Pocket 4P shipped to me."
- "Compare exact-model prices across marketplaces."
- "Avoid accessory listings, wrong variants, and fake low prices with high shipping."
- "Estimate tax and sort by final landed cost."
- "Find marketplace items I can buy and flip profitably on eBay."
- "Research whether a used car is worth flipping on eBay Motors before I inspect it."
- "Track Florida dealer-threshold exposure while evaluating vehicle flips."
- "Track resale leads, inventory, listed items, sold items, and business metrics."

## What It Does

- Searches multiple shopping sources from one MCP interface.
- Normalizes listings into a common schema.
- Separates item price, shipping cost, shipped total, estimated tax, and estimated final total.
- Penalizes accessories, parts, and wrong model variants.
- Handles edge cases like `Pocket 4P` vs `Pocket 4`.
- Scores reseller/arbitrage opportunities using eBay comps, estimated fees, shipping, tax, ROI, and risk.
- Scores vehicle flips separately with eBay Motors listing fees, title/VIN risk, transport, inspection, repairs, storage, and Florida dealer-threshold awareness.
- Tracks a simple resale pipeline: leads, purchases, inventory, listings, sold items, and realized profit.
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
| `get_ebay_sold_comps` | Estimate resale value from eBay comps. Currently returns active-listing comps as a labeled proxy, not fabricated sold data. |
| `calculate_resale_profit` | Calculate eBay-style flip profit, ROI, fees, tax, break-even sale price, and max buy price. |
| `find_arbitrage_opportunities` | Search buy-side marketplaces and rank listings that may be profitable to resell on eBay. |
| `draft_ebay_listing` | Draft an eBay title, description, price hint, shipping guidance, and photo/disclosure checklist. |
| `save_resale_lead` | Save an arbitrage lead into the reseller pipeline. |
| `update_resale_lead_status` | Move a lead through `watching`, `contacted`, `offer_made`, `purchased`, `listed`, `sold`, or `rejected`. |
| `create_inventory_item` | Create a purchased item for inventory tracking. |
| `mark_inventory_listed` | Mark inventory as listed for sale. |
| `mark_inventory_sold` | Mark inventory sold and calculate realized profit. |
| `calculate_business_metrics` | Summarize leads, inventory, invested cash, sold revenue, realized profit, and ROI. |
| `decode_vin` | Validate basic VIN format/check digit and estimate model year/country offline. |
| `calculate_vehicle_flip_profit` | Calculate vehicle flip economics using eBay Motors fees and vehicle-specific costs. |
| `score_vehicle_title_risk` | Score title, VIN, lien, odometer, seller-name, and flood-market risk. |
| `florida_dealer_threshold_status` | Track Florida's three-vehicle dealer-activity presumption threshold. |
| `find_vehicle_arbitrage_opportunities` | Search vehicle leads and rank potential eBay Motors flips. |
| `draft_ebay_motors_listing` | Draft vehicle listing copy, photo checklist, and required disclosures. |
| `save_vehicle_lead` | Save a vehicle research lead. |
| `update_vehicle_status` | Update a vehicle lead status and append notes. |

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

The hosted Worker exposes the reseller and vehicle research tools. Stateful business tools require the Worker's `RESALE_KV` binding; if a deployment has no KV binding, stateless tools such as `find_arbitrage_opportunities`, `find_vehicle_arbitrage_opportunities`, `calculate_resale_profit`, `calculate_vehicle_flip_profit`, `get_ebay_sold_comps`, `decode_vin`, and listing-draft tools still work, while lead/inventory tools return a clear persistence configuration error.

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
SHOPPING_RESALE_STORE_PATH=.shopping-deals/resale-business.json
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

Create and bind KV for resale lead/inventory persistence:

```bash
npx wrangler kv namespace create RESALE_KV
```

Add the returned namespace ID to `wrangler.jsonc`:

```json
{
  "kv_namespaces": [
    {
      "binding": "RESALE_KV",
      "id": "your-kv-namespace-id"
    }
  ]
}
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

Find possible eBay flips:

```json
{
  "query": "Sony a6700 camera body",
  "buy_sources": ["facebook_marketplace", "craigslist", "offerup", "ebay"],
  "location": "40.7128,-74.0060",
  "max_results": 10,
  "max_results_per_source": 25,
  "price_max": 700,
  "min_profit": 75,
  "min_roi_percent": 20,
  "purchase_tax_rate_percent": 8.875,
  "outbound_shipping": 18
}
```

Calculate resale profit directly:

```json
{
  "purchase_price": 500,
  "expected_sale_price": 775,
  "inbound_shipping": 0,
  "outbound_shipping": 18,
  "purchase_tax_rate_percent": 8.875,
  "platform_fee_percent": 13.25,
  "packing_cost": 2
}
```

Save a lead and track it through inventory:

```json
{
  "lead": {
    "title": "Sony a6700 camera body",
    "source": "facebook_marketplace",
    "url": "https://www.facebook.com/marketplace/item/example",
    "asking_price": 575,
    "expected_sale_price": 775,
    "status": "watching"
  }
}
```

Then use:

- `update_resale_lead_status`
- `create_inventory_item`
- `mark_inventory_listed`
- `mark_inventory_sold`
- `calculate_business_metrics`

Research a possible car flip:

```json
{
  "query": "2012 Honda Fit Miami",
  "buy_sources": ["facebook_marketplace", "craigslist", "offerup"],
  "location": "25.7907,-80.1300",
  "max_results": 5,
  "max_results_per_source": 20,
  "price_max": 7000,
  "min_profit": 2000,
  "min_roi_percent": 20,
  "repair_cost": 750,
  "transport_cost": 500,
  "inspection_cost": 150,
  "detail_cost": 150,
  "title_registration_cost": 450,
  "sales_tax_rate_percent": 0,
  "vehicles_sold_or_offered_12mo": 0,
  "title_status": "unknown",
  "has_title_in_hand": null
}
```

Calculate vehicle profit directly:

```json
{
  "purchase_price": 7000,
  "expected_sale_price": 10500,
  "repair_cost": 500,
  "transport_cost": 400,
  "inspection_cost": 150,
  "detail_cost": 150,
  "title_registration_cost": 450
}
```

Track vehicle compliance risk:

```json
{
  "vehicles_sold_or_offered_12mo": 2,
  "planned_new_vehicle_offers": 1
}
```

## Reselling Notes

`get_ebay_sold_comps` is intentionally conservative: today it uses active eBay listing comps as a clearly labeled proxy because the current public eBay Browse API integration does not provide completed/sold listing data. Active comps are useful for initial triage, but confirmed sold comps are better for pricing and sell-through confidence. If you have access to a completed-listing data provider, add it as a dedicated source and keep the `basis` field explicit.

The arbitrage score is a triage signal. Before buying, verify exact model, condition, serial/authenticity, locks/accounts, missing accessories, seller reputation, local safety, shipping dimensions, return risk, and final marketplace fees.

Vehicle flips are scored with a separate model. eBay Motors vehicle listings use package fees instead of the normal item final-value fee model; this server defaults to `$34` at `$15,000` or less and `$79` above `$15,000`, matching eBay's current public help page at the time of implementation. Florida has a low dealer-activity threshold: three or more vehicles bought, sold, dealt, offered, or displayed for sale in a 12-month period creates a prima facie presumption of motor vehicle dealer activity. This server surfaces that threshold, but it does not provide legal advice.

Before buying a vehicle, verify title in hand, VIN match, lien status, odometer, accident/flood history, seller identity, mechanical condition, storage, transport, insurance, tax/title fees, and your legal ability to resell.

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
| `SHOPPING_RESALE_STORE_PATH` | optional | Local JSON path for leads and inventory. Defaults to `.shopping-deals/resale-business.json`. |
| `RESALE_KV` | optional | Cloudflare KV binding for hosted lead/inventory persistence. |

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
- Arbitrage scores are triage signals, not guarantees of sell-through, profit, authenticity, or buyer demand.
- Vehicle opportunity scores are research signals, not legal, title, mechanical, tax, insurance, or dealer-licensing advice.
- Always verify seller reputation, return policy, warranty, shipping, taxes, and authenticity before buying.
- Amazon, Craigslist, Facebook Marketplace, and OfferUp public parsers may break if those sites change markup or block traffic.
- Facebook Marketplace support is experimental. It uses Facebook's public Marketplace web feed with an anonymous page token and requires a local search center.
- Craigslist RSS returns HTTP 403 from Cloudflare Worker egress, so the Worker uses Craigslist static search HTML cards.
- Tax is estimated from a supplied rate. Final checkout tax may differ.
- eBay sold-comps support currently uses active listing comps as a labeled proxy until a true completed/sold-listing data provider is configured.
- Vehicle comps currently use active eBay listing data as a market proxy. Confirm sold results, trim, mileage, title status, accident history, location, and vehicle history before buying.
