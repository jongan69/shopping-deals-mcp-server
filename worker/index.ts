import { createMcpHandler } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

type Env = {
  EBAY_APP_ID?: string;
  EBAY_CERT_ID?: string;
  EBAY_ACCESS_TOKEN?: string;
  EBAY_MARKETPLACE_ID?: string;
  EBAY_USE_SANDBOX?: string;
  SERPAPI_API_KEY?: string;
  CRAIGSLIST_SITES?: string;
  SHOPPING_ENABLE_AMAZON_SCRAPE?: string;
  SHOPPING_HTTP_TIMEOUT_SECONDS?: string;
  SHOPPING_MAX_RESULTS_PER_SOURCE?: string;
  SHOPPING_ESTIMATED_TAX_RATE_PERCENT?: string;
  SHOPPING_TAX_SHIPPING?: string;
  SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE?: string;
  SHOPPING_FACEBOOK_MARKETPLACE_LONGITUDE?: string;
  SHOPPING_FACEBOOK_MARKETPLACE_RADIUS_KM?: string;
  RESALE_KV?: KVNamespace;
};

type Listing = {
  id: string;
  source: string;
  marketplace: string;
  title: string;
  url: string;
  price: number | null;
  shipping_cost?: number | null;
  total_price?: number | null;
  estimated_tax?: number | null;
  total_with_tax?: number | null;
  currency: string;
  condition: string;
  image_url?: string | null;
  seller?: string | null;
  seller_rating?: number | null;
  location?: string | null;
  shipping?: string | null;
  availability?: string | null;
  posted_at?: string | null;
};

type SearchResponse = {
  query: string;
  searched_at: string;
  sources_requested: string[];
  sources_used: string[];
  source_errors: Record<string, string>;
  total_results: number;
  listings: Listing[];
};

type ResaleData = {
  leads: Record<string, Record<string, unknown>>;
  inventory: Record<string, Record<string, unknown>>;
  vehicles: Record<string, Record<string, unknown>>;
};

const SOURCE_NAMES = ["ebay", "facebook_marketplace", "craigslist", "offerup", "amazon"] as const;
const FACEBOOK_GRAPHQL_URL = "https://www.facebook.com/api/graphql/";
const FACEBOOK_MARKETPLACE_SEARCH_DOC_ID = "7111939778879383";
const FACEBOOK_MOBILE_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const ACCESSORY_TERMS = new Set([
  "adapter",
  "accessories",
  "accessory",
  "bag",
  "cable",
  "case",
  "charger",
  "charging",
  "clip",
  "connector",
  "cord",
  "cover",
  "earpad",
  "earpads",
  "film",
  "filter",
  "filters",
  "glass",
  "grip",
  "handle",
  "hinge",
  "hood",
  "kit",
  "kits",
  "kickstand",
  "lens",
  "magnetic",
  "mount",
  "pads",
  "part",
  "parts",
  "protector",
  "repair",
  "replacement",
  "shade",
  "shield",
  "skin",
  "sleeve",
  "stand",
  "strap",
  "sunshade",
  "tripod",
  "viewfinder",
]);
const LEAD_STATUSES = new Set(["watching", "contacted", "offer_made", "purchased", "listed", "sold", "rejected"]);
const DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT = 13.25;
const DEFAULT_PAYMENT_FIXED_FEE = 0.40;
const DEFAULT_PACKING_COST = 2.0;
const EBAY_MOTORS_LOW_LISTING_FEE = 34;
const EBAY_MOTORS_HIGH_LISTING_FEE = 79;
const EBAY_MOTORS_HIGH_PRICE_THRESHOLD = 15000;
const FLORIDA_DEALER_PRESUMPTION_THRESHOLD = 3;
const VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];
const VIN_TRANSLITERATION: Record<string, number> = {
  A: 1, B: 2, C: 3, D: 4, E: 5, F: 6, G: 7, H: 8,
  J: 1, K: 2, L: 3, M: 4, N: 5, P: 7, R: 9,
  S: 2, T: 3, U: 4, V: 5, W: 6, X: 7, Y: 8, Z: 9,
  0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9,
};
const MODEL_YEAR_CODES: Record<string, number> = {
  1: 2001, 2: 2002, 3: 2003, 4: 2004, 5: 2005, 6: 2006, 7: 2007, 8: 2008, 9: 2009,
  A: 2010, B: 2011, C: 2012, D: 2013, E: 2014, F: 2015, G: 2016, H: 2017,
  J: 2018, K: 2019, L: 2020, M: 2021, N: 2022, P: 2023, R: 2024, S: 2025,
  T: 2026, V: 2027, W: 2028, X: 2029, Y: 2030,
};
const WMI_COUNTRIES: Record<string, string> = {
  1: "United States", 2: "Canada", 3: "Mexico", 4: "United States", 5: "United States",
  J: "Japan", K: "South Korea", S: "United Kingdom", W: "Germany", Y: "Sweden/Finland", Z: "Italy",
};

const toolText = (payload: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
});

function createServer(env: Env) {
  const server = new McpServer({ name: "Shopping Deals", version: "0.1.0" });

  server.tool("list_sources", "List shopping source availability.", {}, async () =>
    toolText({ sources: listSources(env) }),
  );

  server.tool(
    "search_products",
    "Search enabled shopping platforms and return normalized product listings.",
    {
      query: z.string().min(1),
      sources: z.array(z.string()).optional(),
      max_results_per_source: z.number().int().positive().optional(),
      price_min: z.number().optional(),
      price_max: z.number().optional(),
      condition: z.string().optional(),
      location: z.string().optional(),
    },
    async (args) => {
      const result = await searchProducts(env, {
        query: args.query,
        sources: args.sources,
        maxResultsPerSource: args.max_results_per_source,
        priceMin: args.price_min,
        priceMax: args.price_max,
        condition: args.condition ?? "any",
        location: args.location,
      });
      return toolText(result);
    },
  );

  server.tool(
    "find_best_deals",
    "Search products and rank the strongest deals with reasons and warnings.",
    {
      query: z.string().min(1),
      sources: z.array(z.string()).optional(),
      max_results: z.number().int().positive().optional(),
      max_results_per_source: z.number().int().positive().optional(),
      price_min: z.number().optional(),
      price_max: z.number().optional(),
      condition: z.string().optional(),
      location: z.string().optional(),
      tax_rate_percent: z.number().optional(),
      tax_on_shipping: z.boolean().optional(),
    },
    async (args) => {
      const response = await searchProducts(env, {
        query: args.query,
        sources: args.sources,
        maxResultsPerSource: args.max_results_per_source,
        priceMin: args.price_min,
        priceMax: args.price_max,
        condition: args.condition ?? "any",
        location: args.location,
      });
      const listings = applyTaxEstimates(env, response.listings, args.tax_rate_percent, args.tax_on_shipping);
      const bestDeals = scoreDeals(args.query, listings).slice(0, args.max_results ?? 10);
      return toolText({
        query: args.query,
        searched_at: response.searched_at,
        source_errors: response.source_errors,
        tax_rate_percent: resolvedTaxRate(env, args.tax_rate_percent),
        tax_on_shipping: resolvedTaxOnShipping(env, args.tax_on_shipping),
        total_results: response.total_results,
        best_deals: bestDeals,
      });
    },
  );

  server.tool(
    "find_cheapest_offers",
    "Search products and return exact-model offers sorted by shipped total when available.",
    {
      query: z.string().min(1),
      sources: z.array(z.string()).optional(),
      max_results: z.number().int().positive().optional(),
      max_results_per_source: z.number().int().positive().optional(),
      price_min: z.number().optional(),
      price_max: z.number().optional(),
      condition: z.string().optional(),
      location: z.string().optional(),
      tax_rate_percent: z.number().optional(),
      tax_on_shipping: z.boolean().optional(),
    },
    async (args) => {
      const response = await searchProducts(env, {
        query: args.query,
        sources: args.sources,
        maxResultsPerSource: args.max_results_per_source,
        priceMin: args.price_min,
        priceMax: args.price_max,
        condition: args.condition ?? "any",
        location: args.location,
      });
      const listings = applyTaxEstimates(env, response.listings, args.tax_rate_percent, args.tax_on_shipping);
      const eligible = listings
        .filter((listing) =>
          effectivePrice(listing) !== null &&
          !isAccessoryMismatch(args.query, listing.title) &&
          !isModelTokenMismatch(args.query, listing.title),
        )
        .sort((a, b) => priceSort(a) - priceSort(b) || a.title.localeCompare(b.title));
      return toolText({
        query: args.query,
        searched_at: response.searched_at,
        source_errors: response.source_errors,
        tax_rate_percent: resolvedTaxRate(env, args.tax_rate_percent),
        tax_on_shipping: resolvedTaxOnShipping(env, args.tax_on_shipping),
        total_results: response.total_results,
        eligible_results: eligible.length,
        cheapest_offers: eligible.slice(0, args.max_results ?? 10),
      });
    },
  );

  server.tool(
    "compare_prices",
    "Group comparable listings and report low, high, and average observed prices.",
    {
      query: z.string().min(1),
      sources: z.array(z.string()).optional(),
      max_results_per_source: z.number().int().positive().optional(),
      price_min: z.number().optional(),
      price_max: z.number().optional(),
      condition: z.string().optional(),
      location: z.string().optional(),
    },
    async (args) => {
      const response = await searchProducts(env, {
        query: args.query,
        sources: args.sources,
        maxResultsPerSource: args.max_results_per_source,
        priceMin: args.price_min,
        priceMax: args.price_max,
        condition: args.condition ?? "any",
        location: args.location,
      });
      return toolText({
        query: args.query,
        searched_at: response.searched_at,
        source_errors: response.source_errors,
        comparisons: comparePrices(response.listings),
      });
    },
  );

  server.tool(
    "get_listing_details",
    "Fetch listing details for sources that support detail lookups.",
    {
      source: z.string(),
      listing_id: z.string(),
    },
    async ({ source, listing_id }) => {
      if (source !== "ebay") {
        return toolText({ error: "Listing details are currently only available for eBay." });
      }
      const listing = await ebayDetails(env, listing_id);
      return toolText(listing ?? { error: "Listing details are unavailable for this item." });
    },
  );

  server.tool(
    "get_ebay_sold_comps",
    "Estimate resale value from eBay comps. Returns active eBay listing comps as a labeled proxy when true sold-comps data is unavailable.",
    {
      query: z.string().min(1),
      max_results: z.number().int().positive().optional(),
      condition: z.string().optional(),
    },
    async (args) => {
      const response = await searchProducts(env, {
        query: args.query,
        sources: ["ebay"],
        maxResultsPerSource: Math.max(args.max_results ?? 20, 25),
        condition: args.condition ?? "any",
      });
      return toolText({
        ...buildResaleComps(args.query, response.listings, args.max_results ?? 20),
        searched_at: response.searched_at,
        source_errors: response.source_errors,
      });
    },
  );

  server.tool(
    "calculate_resale_profit",
    "Calculate net profit, ROI, break-even sale price, and target buy price for a resale flip.",
    {
      purchase_price: z.number().nonnegative(),
      expected_sale_price: z.number().nonnegative(),
      inbound_shipping: z.number().nonnegative().optional(),
      outbound_shipping: z.number().nonnegative().optional(),
      purchase_tax_rate_percent: z.number().nonnegative().optional(),
      platform_fee_percent: z.number().nonnegative().optional(),
      promoted_listing_percent: z.number().nonnegative().optional(),
      payment_fixed_fee: z.number().nonnegative().optional(),
      packing_cost: z.number().nonnegative().optional(),
      misc_cost: z.number().nonnegative().optional(),
      buyer_shipping_charged: z.number().nonnegative().optional(),
    },
    async (args) => toolText(calculateResaleProfit(env, args)),
  );

  server.tool(
    "find_arbitrage_opportunities",
    "Find buy-side listings that may be profitable to flip on eBay.",
    {
      query: z.string().min(1),
      buy_sources: z.array(z.string()).optional(),
      max_results: z.number().int().positive().optional(),
      max_results_per_source: z.number().int().positive().optional(),
      location: z.string().optional(),
      condition: z.string().optional(),
      price_max: z.number().optional(),
      min_profit: z.number().optional(),
      min_roi_percent: z.number().optional(),
      purchase_tax_rate_percent: z.number().nonnegative().optional(),
      outbound_shipping: z.number().nonnegative().optional(),
      platform_fee_percent: z.number().nonnegative().optional(),
      promoted_listing_percent: z.number().nonnegative().optional(),
      packing_cost: z.number().nonnegative().optional(),
    },
    async (args) => {
      const compResponse = await searchProducts(env, {
        query: args.query,
        sources: ["ebay"],
        maxResultsPerSource: 30,
        condition: args.condition ?? "any",
      });
      const resaleComps = {
        ...buildResaleComps(args.query, compResponse.listings, 20),
        searched_at: compResponse.searched_at,
        source_errors: compResponse.source_errors,
      };
      const expectedSalePrice = resaleComps.recommended_resale_price;
      if (expectedSalePrice === null) {
        return toolText({
          query: args.query,
          error: "Could not estimate resale value from eBay comps.",
          resale_comps: resaleComps,
          opportunities: [],
        });
      }
      const buySources = args.buy_sources?.length ? args.buy_sources : ["facebook_marketplace", "craigslist", "offerup", "ebay"];
      const buyResponse = await searchProducts(env, {
        query: args.query,
        sources: buySources,
        maxResultsPerSource: args.max_results_per_source,
        priceMax: args.price_max,
        condition: args.condition ?? "any",
        location: args.location,
      });
      const minProfit = args.min_profit ?? 25;
      const minRoiPercent = args.min_roi_percent ?? 20;
      const opportunities = buyResponse.listings
        .map((listing) => {
          const purchasePrice = effectivePrice(listing);
          if (purchasePrice === null) return null;
          const profit = calculateResaleProfit(env, {
            purchase_price: purchasePrice,
            expected_sale_price: expectedSalePrice,
            inbound_shipping: listing.shipping_cost ?? 0,
            outbound_shipping: args.outbound_shipping ?? 0,
            purchase_tax_rate_percent: args.purchase_tax_rate_percent,
            platform_fee_percent: args.platform_fee_percent,
            promoted_listing_percent: args.promoted_listing_percent,
            packing_cost: args.packing_cost,
          });
          const opportunity = scoreOpportunity(args.query, listing, profit, {
            compCount: resaleComps.comp_count,
            minProfit,
            minRoiPercent,
          });
          return profit.net_profit >= minProfit && profit.roi_percent >= minRoiPercent ? opportunity : null;
        })
        .filter((value): value is ReturnType<typeof scoreOpportunity> => value !== null)
        .sort((a, b) => b.opportunity_score - a.opportunity_score || b.net_profit - a.net_profit || a.risk_score - b.risk_score)
        .slice(0, args.max_results ?? 10);
      return toolText({
        query: args.query,
        searched_at: buyResponse.searched_at,
        buy_sources: buySources,
        sell_side: "ebay",
        source_errors: buyResponse.source_errors,
        resale_comps: resaleComps,
        filters: {
          min_profit: minProfit,
          min_roi_percent: minRoiPercent,
          price_max: args.price_max ?? null,
        },
        opportunities,
      });
    },
  );

  server.tool(
    "draft_ebay_listing",
    "Draft an eBay title, description, pricing hint, and photo/disclosure checklist.",
    {
      product_title: z.string().min(1),
      condition: z.string().optional(),
      known_defects: z.string().optional(),
      included_accessories: z.string().optional(),
      comp_summary: z.record(z.string(), z.unknown()).optional(),
    },
    async (args) => toolText(draftEbayListing(args)),
  );

  server.tool(
    "save_resale_lead",
    "Save an arbitrage lead into the reseller pipeline. Requires RESALE_KV on the Worker.",
    { lead: z.record(z.string(), z.unknown()) },
    async ({ lead }) => toolText(await saveResaleLead(env, lead)),
  );

  server.tool(
    "update_resale_lead_status",
    "Move a reseller lead through watching/contacted/offer/purchased/listed/sold/rejected.",
    {
      lead_id: z.string().min(1),
      status: z.string().min(1),
      notes: z.string().optional(),
    },
    async (args) => toolText(await updateResaleLeadStatus(env, args.lead_id, args.status, args.notes)),
  );

  server.tool(
    "create_inventory_item",
    "Create a purchased inventory item for resale tracking. Requires RESALE_KV on the Worker.",
    { item: z.record(z.string(), z.unknown()) },
    async ({ item }) => toolText(await createInventoryItem(env, item)),
  );

  server.tool(
    "mark_inventory_listed",
    "Mark an inventory item as listed for sale.",
    {
      inventory_id: z.string().min(1),
      listing_url: z.string().min(1),
      asking_price: z.number().nonnegative(),
    },
    async (args) => toolText(await markInventoryListed(env, args.inventory_id, args.listing_url, args.asking_price)),
  );

  server.tool(
    "mark_inventory_sold",
    "Mark inventory sold and calculate realized profit.",
    {
      inventory_id: z.string().min(1),
      sale_price: z.number().nonnegative(),
      sold_url: z.string().optional(),
      outbound_shipping: z.number().nonnegative().optional(),
      platform_fee_percent: z.number().nonnegative().optional(),
    },
    async (args) => toolText(await markInventorySold(env, args)),
  );

  server.tool(
    "calculate_business_metrics",
    "Summarize leads, inventory, revenue, realized profit, and ROI.",
    {},
    async () => toolText(await calculateBusinessMetrics(env)),
  );

  server.tool(
    "decode_vin",
    "Validate and decode basic VIN structure offline.",
    { vin: z.string().min(1) },
    async ({ vin }) => toolText(decodeVin(vin)),
  );

  server.tool(
    "calculate_vehicle_flip_profit",
    "Calculate vehicle flip profit using eBay Motors fees and vehicle-specific costs.",
    {
      purchase_price: z.number().nonnegative(),
      expected_sale_price: z.number().nonnegative(),
      repair_cost: z.number().nonnegative().optional(),
      transport_cost: z.number().nonnegative().optional(),
      inspection_cost: z.number().nonnegative().optional(),
      detail_cost: z.number().nonnegative().optional(),
      title_registration_cost: z.number().nonnegative().optional(),
      sales_tax_rate_percent: z.number().nonnegative().optional(),
      storage_cost: z.number().nonnegative().optional(),
      insurance_cost: z.number().nonnegative().optional(),
      ebay_listing_fee: z.number().nonnegative().optional(),
      deposit_amount: z.number().nonnegative().optional(),
      misc_cost: z.number().nonnegative().optional(),
    },
    async (args) => toolText(calculateVehicleFlipProfit(args)),
  );

  server.tool(
    "score_vehicle_title_risk",
    "Score title, VIN, lien, odometer, seller-name, and flood-market risk.",
    {
      title_status: z.string().optional(),
      has_title_in_hand: z.boolean().nullable().optional(),
      vin: z.string().optional(),
      odometer_discrepancy: z.boolean().optional(),
      seller_name_matches_title: z.boolean().nullable().optional(),
      flood_risk_area: z.boolean().optional(),
      lien_reported: z.boolean().optional(),
    },
    async (args) => toolText(scoreVehicleTitleRisk(args)),
  );

  server.tool(
    "florida_dealer_threshold_status",
    "Track Florida's three-vehicle dealer-activity presumption threshold.",
    {
      vehicles_sold_or_offered_12mo: z.number().int().nonnegative(),
      planned_new_vehicle_offers: z.number().int().nonnegative().optional(),
    },
    async (args) => toolText(floridaDealerThresholdStatus(args)),
  );

  server.tool(
    "find_vehicle_arbitrage_opportunities",
    "Find vehicle opportunities using eBay Motors comps, costs, and title/dealer risk.",
    {
      query: z.string().min(1),
      buy_sources: z.array(z.string()).optional(),
      location: z.string().optional(),
      max_results: z.number().int().positive().optional(),
      max_results_per_source: z.number().int().positive().optional(),
      price_max: z.number().optional(),
      min_profit: z.number().optional(),
      min_roi_percent: z.number().optional(),
      repair_cost: z.number().nonnegative().optional(),
      transport_cost: z.number().nonnegative().optional(),
      inspection_cost: z.number().nonnegative().optional(),
      detail_cost: z.number().nonnegative().optional(),
      title_registration_cost: z.number().nonnegative().optional(),
      sales_tax_rate_percent: z.number().nonnegative().optional(),
      storage_cost: z.number().nonnegative().optional(),
      insurance_cost: z.number().nonnegative().optional(),
      vehicles_sold_or_offered_12mo: z.number().int().nonnegative().optional(),
      title_status: z.string().optional(),
      has_title_in_hand: z.boolean().nullable().optional(),
    },
    async (args) => {
      const compResponse = await searchProducts(env, {
        query: args.query,
        sources: ["ebay"],
        maxResultsPerSource: 50,
      });
      const marketComps = buildVehicleMarketComps(args.query, compResponse.listings, 20);
      const expectedSalePrice = marketComps.recommended_resale_price;
      if (expectedSalePrice === null) {
        return toolText({
          query: args.query,
          error: "Could not estimate vehicle resale value from eBay Motors active comps.",
          market_comps: marketComps,
          opportunities: [],
        });
      }
      const buySources = args.buy_sources?.length ? args.buy_sources : ["facebook_marketplace", "craigslist", "offerup"];
      const buyResponse = await searchProducts(env, {
        query: args.query,
        sources: buySources,
        location: args.location,
        maxResultsPerSource: args.max_results_per_source,
        priceMax: args.price_max,
      });
      const titleRisk = scoreVehicleTitleRisk({
        title_status: args.title_status ?? "unknown",
        has_title_in_hand: args.has_title_in_hand,
        flood_risk_area: true,
      });
      const dealerThreshold = floridaDealerThresholdStatus({
        vehicles_sold_or_offered_12mo: args.vehicles_sold_or_offered_12mo ?? 0,
        planned_new_vehicle_offers: 1,
      });
      const minProfit = args.min_profit ?? 2000;
      const minRoiPercent = args.min_roi_percent ?? 20;
      const opportunities = buyResponse.listings
        .map((listing) => {
          const purchasePrice = effectivePrice(listing);
          if (purchasePrice === null) return null;
          const profit = calculateVehicleFlipProfit({
            purchase_price: purchasePrice,
            expected_sale_price: expectedSalePrice,
            repair_cost: args.repair_cost ?? 0,
            transport_cost: args.transport_cost ?? 500,
            inspection_cost: args.inspection_cost ?? 150,
            detail_cost: args.detail_cost ?? 150,
            title_registration_cost: args.title_registration_cost ?? 450,
            sales_tax_rate_percent: args.sales_tax_rate_percent ?? 0,
            storage_cost: args.storage_cost ?? 0,
            insurance_cost: args.insurance_cost ?? 0,
          });
          const opportunity = scoreVehicleOpportunity(args.query, listing, profit, {
            compCount: marketComps.comp_count,
            minProfit,
            minRoiPercent,
            titleRisk,
            dealerThreshold,
          });
          return profit.net_profit >= minProfit && profit.roi_percent >= minRoiPercent ? opportunity : null;
        })
        .filter((value): value is ReturnType<typeof scoreVehicleOpportunity> => value !== null)
        .sort((a, b) => b.opportunity_score - a.opportunity_score || b.net_profit - a.net_profit || a.risk_score - b.risk_score)
        .slice(0, args.max_results ?? 10);
      return toolText({
        query: args.query,
        searched_at: buyResponse.searched_at,
        buy_sources: buySources,
        sell_side: "ebay_motors",
        source_errors: buyResponse.source_errors,
        market_comps: marketComps,
        assumptions: {
          repair_cost: args.repair_cost ?? 0,
          transport_cost: args.transport_cost ?? 500,
          inspection_cost: args.inspection_cost ?? 150,
          detail_cost: args.detail_cost ?? 150,
          title_registration_cost: args.title_registration_cost ?? 450,
          sales_tax_rate_percent: args.sales_tax_rate_percent ?? 0,
          storage_cost: args.storage_cost ?? 0,
          insurance_cost: args.insurance_cost ?? 0,
          title_status: args.title_status ?? "unknown",
          has_title_in_hand: args.has_title_in_hand ?? null,
        },
        filters: {
          min_profit: minProfit,
          min_roi_percent: minRoiPercent,
          price_max: args.price_max ?? null,
        },
        dealer_threshold: dealerThreshold,
        opportunities,
      });
    },
  );

  server.tool(
    "draft_ebay_motors_listing",
    "Draft eBay Motors listing copy and vehicle photo/disclosure checklist.",
    {
      year: z.number().int().optional(),
      make: z.string().optional(),
      model: z.string().optional(),
      trim: z.string().optional(),
      mileage: z.number().int().nonnegative().optional(),
      title_status: z.string().optional(),
      known_issues: z.string().optional(),
      recent_service: z.string().optional(),
    },
    async (args) => toolText(draftEbayMotorsListing(args)),
  );

  server.tool(
    "save_vehicle_lead",
    "Save a vehicle research lead into the reseller pipeline. Requires RESALE_KV on the Worker.",
    { vehicle: z.record(z.string(), z.unknown()) },
    async ({ vehicle }) => toolText(await saveVehicleLead(env, vehicle)),
  );

  server.tool(
    "update_vehicle_status",
    "Update a vehicle lead status and append optional notes.",
    {
      vehicle_id: z.string().min(1),
      status: z.string().min(1),
      notes: z.string().optional(),
    },
    async (args) => toolText(await updateVehicleStatus(env, args.vehicle_id, args.status, args.notes)),
  );

  return server;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({
        ok: true,
        name: "shopping-deals-mcp",
        mcp: `${url.origin}/mcp`,
        sources: listSources(env),
        resale_persistence: Boolean(env.RESALE_KV),
      });
    }

    const server = createServer(env);
    return createMcpHandler(server, {
      route: "/mcp",
      enableJsonResponse: true,
      corsOptions: {
        origin: "*",
        methods: "GET, POST, DELETE, OPTIONS",
        headers: "Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version",
        exposeHeaders: "Mcp-Session-Id",
      },
    })(request, env, ctx);
  },
} satisfies ExportedHandler<Env>;

function listSources(env: Env) {
  return [
    {
      name: "ebay",
      display_name: "eBay",
      available: Boolean(env.EBAY_ACCESS_TOKEN || (env.EBAY_APP_ID && env.EBAY_CERT_ID)),
      requires: env.EBAY_ACCESS_TOKEN || (env.EBAY_APP_ID && env.EBAY_CERT_ID)
        ? []
        : ["EBAY_ACCESS_TOKEN or EBAY_APP_ID + EBAY_CERT_ID"],
      notes: "Uses the official eBay Browse API.",
    },
    {
      name: "facebook_marketplace",
      display_name: "Facebook Marketplace",
      available: true,
      requires: facebookCoordinates(env) ? [] : [
        "location as latitude,longitude or SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE/LONGITUDE",
      ],
      notes: "Experimental public Facebook Marketplace parser. Requires a local search center and may fail if Facebook changes or blocks anonymous Marketplace requests.",
    },
    {
      name: "craigslist",
      display_name: "Craigslist",
      available: true,
      requires: [],
      notes: `Configured sites: ${craigslistSites(env).join(", ")}. Uses Craigslist search HTML with structured listing data.`,
    },
    {
      name: "offerup",
      display_name: "OfferUp",
      available: true,
      requires: [],
      notes: "Public OfferUp search parser. Results are local and may vary by inferred location.",
    },
    {
      name: "amazon",
      display_name: "Amazon",
      available: boolEnv(env.SHOPPING_ENABLE_AMAZON_SCRAPE, false),
      requires: boolEnv(env.SHOPPING_ENABLE_AMAZON_SCRAPE, false)
        ? []
        : ["SHOPPING_ENABLE_AMAZON_SCRAPE=true"],
      notes: "Public HTML parser. Amazon may block automated requests.",
    },
  ];
}

async function searchProducts(
  env: Env,
  options: {
    query: string;
    sources?: string[];
    maxResultsPerSource?: number;
    priceMin?: number;
    priceMax?: number;
    condition?: string;
    location?: string;
  },
): Promise<SearchResponse> {
  const selected = options.sources?.length ? options.sources : [...SOURCE_NAMES];
  const limit = options.maxResultsPerSource ?? intEnv(env.SHOPPING_MAX_RESULTS_PER_SOURCE, 25);
  const sourceErrors: Record<string, string> = {};

  const tasks = selected.map(async (source) => {
    try {
      if (source === "ebay") {
        return { source, listings: await ebaySearch(env, options.query, limit, options.priceMin, options.priceMax) };
      }
      if (source === "facebook_marketplace") {
        return {
          source,
          listings: await facebookMarketplaceSearch(
            env,
            options.query,
            limit,
            options.location,
            options.priceMin,
            options.priceMax,
          ),
        };
      }
      if (source === "craigslist") {
        return { source, listings: await craigslistSearch(env, options.query, limit, options.priceMin, options.priceMax) };
      }
      if (source === "offerup") {
        return { source, listings: await offerupSearch(env, options.query, limit, options.priceMin, options.priceMax) };
      }
      if (source === "amazon") {
        if (!boolEnv(env.SHOPPING_ENABLE_AMAZON_SCRAPE, false)) {
          throw new Error("Source is not configured. Requires: SHOPPING_ENABLE_AMAZON_SCRAPE=true");
        }
        return { source, listings: await amazonSearch(env, options.query, limit, options.priceMin, options.priceMax) };
      }
      throw new Error("Unknown source.");
    } catch (error) {
      sourceErrors[source] = `${error instanceof Error ? error.name : "Error"}: ${error instanceof Error ? error.message : String(error)}`;
      return { source, listings: [] as Listing[] };
    }
  });

  const results = await Promise.all(tasks);
  const listings = dedupeListings(results.flatMap((result) => result.listings));
  listings.sort((a, b) => searchResultSort(options.query, a, b));

  return {
    query: options.query,
    searched_at: new Date().toISOString(),
    sources_requested: selected,
    sources_used: results.filter((result) => !sourceErrors[result.source]).map((result) => result.source),
    source_errors: sourceErrors,
    total_results: listings.length,
    listings,
  };
}

async function ebaySearch(
  env: Env,
  query: string,
  maxResults: number,
  priceMin?: number,
  priceMax?: number,
): Promise<Listing[]> {
  const token = await ebayToken(env);
  if (!token) return [];

  const searchLimit = Math.min(Math.max(maxResults, 50), 200);
  const variants = ebayQueryVariants(query);
  const batches = await Promise.all(
    variants.flatMap((variant) => [
      ebaySearchOnce(env, token, variant, searchLimit, priceMin, priceMax),
      ebaySearchOnce(env, token, variant, searchLimit, priceMin, priceMax, "price"),
    ]),
  );
  const listings = dedupeListings(batches.flat());
  listings.sort((a, b) => ebayCandidateSort(query, a, b));
  return listings.slice(0, maxResults);
}

async function ebaySearchOnce(
  env: Env,
  token: string,
  query: string,
  maxResults: number,
  priceMin?: number,
  priceMax?: number,
  sort?: string,
): Promise<Listing[]> {
  const params = new URLSearchParams({ q: query, limit: String(Math.min(maxResults, 200)) });
  if (sort) params.set("sort", sort);
  const filters: string[] = [];
  if (priceMin !== undefined || priceMax !== undefined) {
    filters.push(`price:[${priceMin !== undefined ? priceMin.toFixed(2) : ""}..${priceMax !== undefined ? priceMax.toFixed(2) : ""}]`);
  }
  if (filters.length) params.set("filter", filters.join(","));

  const base = ebayBrowseBase(env);
  const response = await timedFetch(env, `${base}/item_summary/search?${params}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-EBAY-C-MARKETPLACE-ID": env.EBAY_MARKETPLACE_ID ?? "EBAY_US",
    },
  });
  if (!response.ok) throw new Error(`eBay search failed: HTTP ${response.status}`);
  const data = (await response.json()) as { itemSummaries?: Record<string, unknown>[] };
  return (data.itemSummaries ?? []).map((item) => ebayListing(item)).filter((listing) => listing.id && listing.title && listing.url);
}

async function ebayDetails(env: Env, listingId: string): Promise<Listing | null> {
  const token = await ebayToken(env);
  if (!token) return null;
  const response = await timedFetch(env, `${ebayBrowseBase(env)}/item/${encodeURIComponent(listingId)}`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "X-EBAY-C-MARKETPLACE-ID": env.EBAY_MARKETPLACE_ID ?? "EBAY_US",
    },
  });
  if (!response.ok) return null;
  return ebayListing((await response.json()) as Record<string, unknown>);
}

async function ebayToken(env: Env): Promise<string | null> {
  if (env.EBAY_ACCESS_TOKEN) return env.EBAY_ACCESS_TOKEN;
  if (!env.EBAY_APP_ID || !env.EBAY_CERT_ID) return null;

  const credentials = btoa(`${env.EBAY_APP_ID}:${env.EBAY_CERT_ID}`);
  const response = await timedFetch(env, ebayOauthUrl(env), {
    method: "POST",
    headers: {
      Authorization: `Basic ${credentials}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      scope: "https://api.ebay.com/oauth/api_scope",
    }),
  });
  if (!response.ok) throw new Error(`eBay OAuth failed: HTTP ${response.status}`);
  const data = (await response.json()) as { access_token?: string };
  return data.access_token ?? null;
}

function ebayListing(item: Record<string, unknown>): Listing {
  const price = objectValue(item.price);
  const seller = objectValue(item.seller);
  const image = objectValue(item.image);
  const priceAmount = amount(price);
  const shippingCost = ebayShippingCost(item);
  return {
    id: String(item.itemId ?? item.legacyItemId ?? ""),
    source: "ebay",
    marketplace: "eBay",
    title: String(item.title ?? "").trim(),
    url: String(item.itemWebUrl ?? ""),
    price: priceAmount,
    shipping_cost: shippingCost,
    total_price: totalPrice(priceAmount, shippingCost),
    currency: String(price?.currency ?? "USD"),
    condition: normalizeCondition(item.condition),
    image_url: typeof image?.imageUrl === "string" ? image.imageUrl : null,
    seller: typeof seller?.username === "string" ? seller.username : null,
    seller_rating: parsePrice(seller?.feedbackPercentage),
    location: locationText(objectValue(item.itemLocation)),
    shipping: shippingText(item),
    availability: Array.isArray(item.buyingOptions) ? String(item.buyingOptions[0] ?? "") : null,
  };
}

async function amazonSearch(env: Env, query: string, limit: number, priceMin?: number, priceMax?: number): Promise<Listing[]> {
  const response = await timedFetch(env, `https://www.amazon.com/s?k=${encodeURIComponent(query)}`, {
    headers: browserHeaders("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
  });
  if (!response.ok) throw new Error(`Amazon search failed: HTTP ${response.status}`);
  const html = await response.text();
  const cards = html.split('data-component-type="s-search-result"').slice(1);
  const listings: Listing[] = [];

  for (const card of cards) {
    const asin = match(card, /data-asin="([^"]+)"/);
    const href = decodeHtml(match(card, /<a[^>]+class="[^"]*a-link-normal s-line-clamp-2[^"]*"[^>]+href="([^"]+)"/));
    const titleRaw =
      stripTags(match(card, /<a[^>]+class="[^"]*a-link-normal s-line-clamp-2[^"]*"[^>]*>([\s\S]*?)<\/a>/)) ||
      stripTags(match(card, /data-cy="title-recipe"[\s\S]*?>([\s\S]*?)<\/div>/));
    const title = cleanAmazonTitle(decodeHtml(titleRaw));
    const price = parsePrice(decodeHtml(match(card, /<span class="a-offscreen">([^<]+)<\/span>/)));
    if (!title || !href) continue;
    if (price !== null && priceMin !== undefined && price < priceMin) continue;
    if (price !== null && priceMax !== undefined && price > priceMax) continue;

    listings.push({
      id: asin || href || title,
      source: "amazon",
      marketplace: "Amazon",
      title,
      url: new URL(href, "https://www.amazon.com").toString(),
      price,
      currency: "USD",
      condition: "new",
      image_url: decodeHtml(match(card, /<img[^>]+class="[^"]*s-image[^"]*"[^>]+src="([^"]+)"/)) || null,
      seller: "Amazon",
    });
    if (listings.length >= limit) break;
  }
  return listings;
}

async function facebookMarketplaceSearch(
  env: Env,
  query: string,
  limit: number,
  location?: string,
  priceMin?: number,
  priceMax?: number,
): Promise<Listing[]> {
  const coordinates = facebookCoordinates(env, location);
  if (!coordinates) return [];

  const headers = facebookHeaders();
  const { token, referer } = await facebookLsdToken(env, query, headers);
  const variables = {
    count: Math.max(1, Math.min(limit, 24)),
    params: {
      bqf: { callsite: "COMMERCE_MKTPLACE_WWW", query },
      browse_request_params: {
        commerce_enable_local_pickup: true,
        commerce_enable_shipping: true,
        commerce_search_and_rp_available: true,
        commerce_search_and_rp_condition: null,
        commerce_search_and_rp_ctime_days: null,
        filter_location_latitude: coordinates.latitude,
        filter_location_longitude: coordinates.longitude,
        filter_price_lower_bound: 0,
        filter_price_upper_bound: 214748364700,
        filter_radius_km: intEnv(env.SHOPPING_FACEBOOK_MARKETPLACE_RADIUS_KM, 16),
      },
      custom_request_params: { surface: "SEARCH" },
    },
  };
  const response = await timedFetch(env, FACEBOOK_GRAPHQL_URL, {
    method: "POST",
    headers: {
      ...headers,
      Accept: "*/*",
      "Content-Type": "application/x-www-form-urlencoded",
      Origin: "https://www.facebook.com",
      Referer: referer,
      "x-fb-lsd": token,
    },
    body: new URLSearchParams({
      av: "0",
      __user: "0",
      __a: "1",
      __req: "1",
      __comet_req: "15",
      lsd: token,
      jazoest: "21000",
      fb_api_caller_class: "RelayModern",
      fb_api_req_friendly_name: "CometMarketplaceSearchContentContainerQuery",
      variables: JSON.stringify(variables),
      server_timestamps: "true",
      doc_id: FACEBOOK_MARKETPLACE_SEARCH_DOC_ID,
    }),
  });
  if (!response.ok) throw new Error(`Facebook Marketplace search failed: HTTP ${response.status}`);
  const payload = JSON.parse((await response.text()).replace(/^for \(;;\);/, ""));
  if (payload.error) {
    throw new Error(`Facebook Marketplace search failed: ${payload.errorSummary ?? payload.errorDescription ?? payload.error}`);
  }
  return parseFacebookMarketplace(payload, limit, priceMin, priceMax);
}

async function facebookLsdToken(env: Env, query: string, headers: Record<string, string>): Promise<{ token: string; referer: string }> {
  const urls = [
    `https://www.facebook.com/marketplace/nyc/search/?query=${encodeURIComponent(query)}`,
    `https://www.facebook.com/marketplace/search/?query=${encodeURIComponent(query)}`,
    "https://www.facebook.com/marketplace/",
  ];
  let lastStatus = "";
  for (let attempt = 0; attempt < 2; attempt += 1) {
    for (const url of urls) {
      const response = await timedFetch(env, url, { headers, redirect: "follow" });
      if (!response.ok) {
        lastStatus = `HTTP ${response.status} from ${url}`;
        continue;
      }
      const token = extractFacebookLsdToken(await response.text());
      lastStatus = `HTTP ${response.status} from ${response.url}`;
      if (token) return { token, referer: response.url };
    }
  }
  throw new Error(`Facebook Marketplace search token was not present in public page (${lastStatus}).`);
}

function parseFacebookMarketplace(data: Record<string, unknown>, limit: number, priceMin?: number, priceMax?: number): Listing[] {
  const root = objectValue(data.data);
  const search = objectValue(root?.marketplace_search);
  const feed = objectValue(search?.feed_units);
  const edges = Array.isArray(feed?.edges) ? feed.edges : [];
  const listings: Listing[] = [];
  const seen = new Set<string>();

  for (const edge of edges) {
    const node = objectValue(objectValue(edge)?.node);
    if (node?.__typename !== "MarketplaceFeedListingStoryObject") continue;
    const item = objectValue(node.listing);
    if (!item) continue;
    const id = String(item.id ?? "").trim();
    const title = String(item.marketplace_listing_title ?? item.title ?? "").trim();
    if (!id || !title || seen.has(id)) continue;
    seen.add(id);
    const price = facebookListingPrice(item);
    if (price !== null && priceMin !== undefined && price < priceMin) continue;
    if (price !== null && priceMax !== undefined && price > priceMax) continue;
    listings.push({
      id,
      source: "facebook_marketplace",
      marketplace: "Facebook Marketplace",
      title,
      url: `https://www.facebook.com/marketplace/item/${id}`,
      price,
      currency: "USD",
      condition: "used",
      image_url: facebookListingImage(item),
      location: facebookListingLocation(item),
      shipping: item.is_shipping_offered ? "Shipping offered" : "Local pickup",
      availability: item.is_pending ? "pending" : null,
    });
    if (listings.length >= limit) break;
  }
  return listings;
}

async function offerupSearch(env: Env, query: string, limit: number, priceMin?: number, priceMax?: number): Promise<Listing[]> {
  const response = await timedFetch(env, `https://offerup.com/search?q=${encodeURIComponent(query)}`, {
    headers: browserHeaders("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
  });
  if (!response.ok) throw new Error(`OfferUp search failed: HTTP ${response.status}`);
  const html = await response.text();
  const jsonText = match(html, /<script[^>]+id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
  if (!jsonText) return [];
  const data = JSON.parse(jsonText) as unknown;
  const rawListings: Record<string, unknown>[] = [];
  collectOfferUpListings(data, rawListings);

  const listings: Listing[] = [];
  const seen = new Set<string>();
  for (const item of rawListings) {
    const id = String(item.listingId ?? item.id ?? "");
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const price = parsePrice(item.price);
    if (price !== null && priceMin !== undefined && price < priceMin) continue;
    if (price !== null && priceMax !== undefined && price > priceMax) continue;
    const image = objectValue(item.image);
    listings.push({
      id,
      source: "offerup",
      marketplace: "OfferUp",
      title: String(item.title ?? "").trim(),
      url: `https://offerup.com/item/detail/${id}`,
      price,
      currency: "USD",
      condition: "used",
      image_url: typeof image?.url === "string" ? image.url : null,
      location: typeof item.locationName === "string" ? item.locationName : null,
      shipping: "Local pickup",
    });
    if (listings.length >= limit) break;
  }
  return listings.filter((listing) => listing.title);
}

async function craigslistSearch(env: Env, query: string, limit: number, priceMin?: number, priceMax?: number): Promise<Listing[]> {
  const sites = craigslistSites(env);
  const errors: string[] = [];
  const listings: Listing[] = [];
  const perSiteLimit = Math.max(1, Math.ceil(limit / Math.max(sites.length, 1)));

  for (const site of sites) {
    const params = new URLSearchParams({ query, sort: "date" });
    if (priceMin !== undefined) params.set("min_price", String(Math.floor(priceMin)));
    if (priceMax !== undefined) params.set("max_price", String(Math.floor(priceMax)));
    const response = await timedFetch(env, `https://${site}.craigslist.org/search/sss?${params}`, {
      headers: browserHeaders("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    });
    if (!response.ok) {
      errors.push(`${site}: HTTP ${response.status}`);
      continue;
    }
    const parsed = parseCraigslistHtml(site, await response.text(), perSiteLimit);
    if (!parsed.length) errors.push(`${site}: no listings parsed from HTML`);
    listings.push(...parsed);
    if (listings.length >= limit) break;
  }
  if (!listings.length && errors.length) {
    const fallback = await craigslistRssOrJinaSearch(env, query, limit, priceMin, priceMax);
    if (fallback.length) return applyPriceBounds(fallback, priceMin, priceMax).slice(0, limit);
  }
  if (!listings.length && errors.length) throw new Error(errors.join("; "));
  return applyPriceBounds(dedupeListings(listings), priceMin, priceMax).slice(0, limit);
}

async function craigslistRssOrJinaSearch(
  env: Env,
  query: string,
  limit: number,
  priceMin?: number,
  priceMax?: number,
): Promise<Listing[]> {
  const listings: Listing[] = [];
  const sites = craigslistSites(env);
  const perSiteLimit = Math.max(limit, Math.ceil(limit / Math.max(sites.length, 1)));
  const errors: string[] = [];
  for (const site of sites) {
    const rssParams = new URLSearchParams({ query, format: "rss", sort: "date" });
    if (priceMin !== undefined) rssParams.set("min_price", String(Math.floor(priceMin)));
    if (priceMax !== undefined) rssParams.set("max_price", String(Math.floor(priceMax)));
    const rssResponse = await timedFetch(env, `https://${site}.craigslist.org/search/sss?${rssParams}`, {
      headers: browserHeaders("application/rss+xml, application/xml, text/xml, */*"),
    });
    if (rssResponse.ok) {
      listings.push(...parseCraigslistRss(site, await rssResponse.text(), perSiteLimit));
      if (listings.length >= limit) break;
      continue;
    }
    errors.push(`${site} RSS fallback: HTTP ${rssResponse.status}`);

    const params = new URLSearchParams({ query, sort: "date" });
    const jinaUrl = `https://r.jina.ai/http://${site}.craigslist.org/search/sss?${params}`;
    const response = await timedFetch(env, jinaUrl, {
      headers: browserHeaders("text/plain, */*"),
    });
    if (!response.ok) {
      errors.push(`${site} Jina fallback: HTTP ${response.status}`);
      continue;
    }
    const markdown = await response.text();
    const parsed = parseCraigslistMarkdown(site, markdown, perSiteLimit);
    if (!parsed.length) errors.push(`${site} Jina fallback: no listing links parsed`);
    const siteListings = parsed
      .filter((listing) => listing.price === null || (
        (priceMin === undefined || listing.price >= priceMin) &&
        (priceMax === undefined || listing.price <= priceMax)
      ));
    listings.push(...siteListings);
    if (listings.length >= limit) break;
  }
  const deduped = dedupeListings(listings).slice(0, limit);
  if (!deduped.length && errors.length) throw new Error(errors.join("; "));
  return deduped;
}

function parseCraigslistHtml(site: string, html: string, limit: number): Listing[] {
  const cards = [...html.matchAll(/<li[^>]+class=["'][^"']*cl-static-search-result[^"']*["'][^>]*>([\s\S]*?)<\/li>/g)];
  return cards.slice(0, limit).map((found) => {
    const card = found[1] ?? "";
    const title = decodeHtml(stripTags(match(card, /<div[^>]+class=["']title["'][^>]*>([\s\S]*?)<\/div>/))).trim();
    const url = decodeHtml(match(card, /<a[^>]+href=["']([^"']+)["']/));
    const priceText = decodeHtml(stripTags(match(card, /<div[^>]+class=["']price["'][^>]*>([\s\S]*?)<\/div>/))).trim();
    const location = decodeHtml(stripTags(match(card, /<div[^>]+class=["']location["'][^>]*>([\s\S]*?)<\/div>/))).trim();
    return {
      id: url.split("/").pop() || title,
      source: "craigslist",
      marketplace: `Craigslist ${site}`,
      title,
      url,
      price: priceText.toLowerCase() === "free" ? 0 : parsePrice(priceText),
      currency: "USD",
      condition: "used",
      location: location ? `${site}: ${location}` : site,
      shipping: "Local pickup",
    };
  }).filter((listing) => listing.title && listing.url);
}

function parseCraigslistRss(site: string, rss: string, limit: number): Listing[] {
  const items = rss.split("<item").slice(1);
  return items.slice(0, limit).map((item) => {
    const title = decodeHtml(cdata(match(item, /<title>([\s\S]*?)<\/title>/))).trim();
    const url = decodeHtml(match(item, /<link>([\s\S]*?)<\/link>/)).trim();
    return {
      id: url.split("/").pop()?.replace(".html", "") || title,
      source: "craigslist",
      marketplace: `Craigslist ${site}`,
      title,
      url,
      price: parsePrice(title) ?? parsePrice(cdata(match(item, /<description>([\s\S]*?)<\/description>/))),
      currency: "USD",
      condition: "used",
      location: site,
      shipping: "Local pickup",
      posted_at: match(item, /<pubDate>([\s\S]*?)<\/pubDate>/) || null,
    };
  }).filter((listing) => listing.title && listing.url);
}

function parseCraigslistMarkdown(site: string, markdown: string, limit: number): Listing[] {
  const lines = markdown.split(/\r?\n/).map((line) => line.trim());
  const listings: Listing[] = [];
  for (let index = 0; index < lines.length && listings.length < limit; index += 1) {
    const line = lines[index] ?? "";
    if (!line || line.startsWith("[!") || line.includes("craigslist.org/area/")) continue;
    const found = line.match(/^\[([^\]]+)\]\((https?:\/\/(?:www\.)?craigslist\.org\/view\/d\/[^)]+)\)$/);
    if (!found) continue;
    const [, title, url] = found;
    const lookahead = lines.slice(index + 1, index + 6).filter(Boolean);
    const priceLine = lookahead.find((value) => /^\$[0-9,]+(?:\.[0-9]{2})?$/.test(value) || value.toLowerCase() === "free");
    const detailLine = lookahead.find((value) => /(?:\d+h ago|\d+\/\d+)/i.test(value)) ?? null;
    listings.push({
      id: url.split("/").pop() || title,
      source: "craigslist",
      marketplace: `Craigslist ${site}`,
      title: decodeHtml(title).trim(),
      url,
      price: priceLine?.toLowerCase() === "free" ? 0 : parsePrice(priceLine),
      currency: "USD",
      condition: "used",
      location: detailLine ? `${site}: ${detailLine}` : site,
      shipping: "Local pickup",
      posted_at: detailLine,
    });
  }
  return listings;
}

function scoreDeals(query: string, listings: Listing[]) {
  const comparablePrices = listings
    .filter((listing) => effectivePrice(listing) !== null && !isAccessoryMismatch(query, listing.title) && !isModelTokenMismatch(query, listing.title))
    .map((listing) => effectivePrice(listing) as number);
  const prices = comparablePrices.length ? comparablePrices : listings.filter((listing) => effectivePrice(listing) !== null).map((listing) => effectivePrice(listing) as number);
  const low = prices.length ? Math.min(...prices) : null;
  const high = prices.length ? Math.max(...prices) : null;
  const avg = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null;

  return listings.map((listing) => {
    const warnings: string[] = [];
    const relevance = titleSimilarity(query, listing.title);
    const listingPrice = effectivePrice(listing);
    let priceScore = 35;
    if (listingPrice === null) {
      priceScore = 15;
      warnings.push("No price was available, so the deal score is less certain.");
    } else if (low !== null && high !== null && low !== high) {
      priceScore = 55 * (1 - ((listingPrice - low) / (high - low)));
    } else if (avg !== null) {
      priceScore = 45;
    }

    const accessoryMismatch = isAccessoryMismatch(query, listing.title);
    const modelMismatch = isModelTokenMismatch(query, listing.title);
    if (accessoryMismatch) warnings.push("Looks like an accessory, repair part, or replacement component.");
    if (modelMismatch) warnings.push("Missing an exact model/variant token from the query.");
    if (relevance < 0.35) warnings.push("Title match is weak; verify this is the exact product.");
    if (listing.source === "craigslist") warnings.push("Local marketplace listing; verify seller identity and availability.");

    const sourceBonus = listing.source === "ebay" ? 10 : listing.source === "amazon" ? 6 : listing.source === "craigslist" ? 4 : 3;
    const conditionBonus = ["new", "open_box", "refurbished"].includes(listing.condition) ? 8 : listing.condition === "used" ? 4 : 0;
    const shippingBonus = listing.shipping?.toLowerCase().includes("free") ? 5 : listing.shipping?.toLowerCase().includes("pickup") ? 2 : 0;
    const penalty = (accessoryMismatch ? 70 : 0) + (modelMismatch ? 65 : 0);
    let score = clamp(priceScore + relevance * 22 + sourceBonus + conditionBonus + shippingBonus - penalty, 0, 100);
    if (accessoryMismatch) score = Math.min(score, 30);
    if (modelMismatch) score = Math.min(score, 35);
    return {
      listing,
      deal_score: Math.round(score * 100) / 100,
      rank_reason: rankReason(listing, low, avg, relevance),
      warnings,
    };
  }).sort((a, b) => b.deal_score - a.deal_score);
}

function comparePrices(listings: Listing[]) {
  const groups = new Map<string, Listing[]>();
  for (const listing of listings) {
    const key = productKey(listing.title) || normalizeText(listing.title);
    groups.set(key, [...(groups.get(key) ?? []), listing]);
  }
  return [...groups.entries()].map(([group_key, groupListings]) => {
    const prices = groupListings.filter((listing) => listing.price !== null).map((listing) => listing.price as number);
    return {
      group_key,
      title: groupListings[0]?.title ?? group_key,
      count: groupListings.length,
      low_price: prices.length ? Math.min(...prices) : null,
      high_price: prices.length ? Math.max(...prices) : null,
      average_price: prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : null,
      sources: [...new Set(groupListings.map((listing) => listing.source))].sort(),
      listings: groupListings,
    };
  }).sort((a, b) => priceSortValue(a.low_price) - priceSortValue(b.low_price) || b.count - a.count);
}

function buildResaleComps(query: string, listings: Listing[], maxComps: number) {
  const eligible = listings
    .filter((listing) =>
      effectivePrice(listing) !== null &&
      !isAccessoryMismatch(query, listing.title) &&
      !isModelTokenMismatch(query, listing.title) &&
      titleSimilarity(query, listing.title) >= 0.35,
    )
    .sort((a, b) => priceSort(a) - priceSort(b) || a.title.localeCompare(b.title));
  const prices = eligible.map((listing) => effectivePrice(listing)).filter((price): price is number => price !== null);
  return {
    query,
    basis: "active_ebay_listing_proxy",
    limitation: "Current implementation uses active eBay listings as resale comps. True sold-comps support requires a completed/sold-listing data source.",
    comp_count: prices.length,
    low_price: prices.length ? Math.min(...prices) : null,
    median_price: prices.length ? medianNumber(prices) : null,
    high_price: prices.length ? Math.max(...prices) : null,
    average_price: prices.length ? roundMoney(prices.reduce((a, b) => a + b, 0) / prices.length) : null,
    recommended_resale_price: recommendedResalePrice(prices),
    sell_through_confidence: sellThroughConfidence(prices.length, prices),
    comps: eligible.slice(0, maxComps),
  };
}

function calculateResaleProfit(
  env: Env,
  args: {
    purchase_price: number;
    expected_sale_price: number;
    inbound_shipping?: number;
    outbound_shipping?: number;
    purchase_tax_rate_percent?: number;
    platform_fee_percent?: number;
    promoted_listing_percent?: number;
    payment_fixed_fee?: number;
    packing_cost?: number;
    misc_cost?: number;
    buyer_shipping_charged?: number;
  },
) {
  const inboundShipping = args.inbound_shipping ?? 0;
  const outboundShipping = args.outbound_shipping ?? 0;
  const taxRate = args.purchase_tax_rate_percent ?? resolvedTaxRate(env, undefined) ?? 0;
  const platformFeePercent = args.platform_fee_percent ?? DEFAULT_EBAY_FINAL_VALUE_FEE_PERCENT;
  const promotedListingPercent = args.promoted_listing_percent ?? 0;
  const paymentFixedFee = args.payment_fixed_fee ?? DEFAULT_PAYMENT_FIXED_FEE;
  const packingCost = args.packing_cost ?? DEFAULT_PACKING_COST;
  const miscCost = args.misc_cost ?? 0;
  const buyerShippingCharged = args.buyer_shipping_charged ?? 0;
  const purchaseTax = roundMoney((args.purchase_price + inboundShipping) * (taxRate / 100));
  const grossRevenue = args.expected_sale_price + buyerShippingCharged;
  const feeBasis = args.expected_sale_price + buyerShippingCharged;
  const platformFee = roundMoney(feeBasis * (platformFeePercent / 100));
  const promotedFee = roundMoney(feeBasis * (promotedListingPercent / 100));
  const totalCost = roundMoney(
    args.purchase_price +
      inboundShipping +
      purchaseTax +
      outboundShipping +
      packingCost +
      miscCost +
      platformFee +
      promotedFee +
      paymentFixedFee,
  );
  const netProfit = roundMoney(grossRevenue - totalCost);
  const cashInvested = roundMoney(args.purchase_price + inboundShipping + purchaseTax + packingCost + miscCost);
  const roiPercent = cashInvested ? roundMoney((netProfit / cashInvested) * 100) : 0;
  const feeRate = (platformFeePercent + promotedListingPercent) / 100;
  const fixedCostsBeforeSale = args.purchase_price + inboundShipping + purchaseTax + outboundShipping + packingCost + miscCost + paymentFixedFee;
  const breakEvenSalePrice = roundMoney(Math.ceil((fixedCostsBeforeSale / Math.max(1 - feeRate, 0.01)) * 100) / 100);
  return {
    purchase_price: roundMoney(args.purchase_price),
    expected_sale_price: roundMoney(args.expected_sale_price),
    gross_revenue: roundMoney(grossRevenue),
    purchase_tax: purchaseTax,
    platform_fee: platformFee,
    promoted_listing_fee: promotedFee,
    payment_fixed_fee: roundMoney(paymentFixedFee),
    packing_cost: roundMoney(packingCost),
    total_cost: totalCost,
    net_profit: netProfit,
    roi_percent: roiPercent,
    break_even_sale_price: breakEvenSalePrice,
    max_buy_price_for_20_roi: maxBuyPriceForTarget({
      expectedSalePrice: args.expected_sale_price,
      targetRoiPercent: 20,
      inboundShipping,
      outboundShipping,
      purchaseTaxRatePercent: taxRate,
      platformFeePercent,
      promotedListingPercent,
      paymentFixedFee,
      packingCost,
      miscCost,
      buyerShippingCharged,
    }),
  };
}

function maxBuyPriceForTarget(args: {
  expectedSalePrice: number;
  targetRoiPercent: number;
  inboundShipping: number;
  outboundShipping: number;
  purchaseTaxRatePercent: number;
  platformFeePercent: number;
  promotedListingPercent: number;
  paymentFixedFee: number;
  packingCost: number;
  miscCost: number;
  buyerShippingCharged: number;
}): number {
  const taxRate = args.purchaseTaxRatePercent / 100;
  const targetRoi = args.targetRoiPercent / 100;
  const feeRate = (args.platformFeePercent + args.promotedListingPercent) / 100;
  const revenue = args.expectedSalePrice + args.buyerShippingCharged;
  const saleFees = (args.expectedSalePrice + args.buyerShippingCharged) * feeRate + args.paymentFixedFee;
  const fixedCosts = args.inboundShipping * (1 + taxRate) + args.outboundShipping + args.packingCost + args.miscCost + saleFees;
  return roundMoney(Math.max((revenue - fixedCosts) / (1 + taxRate + targetRoi), 0));
}

function scoreOpportunity(
  query: string,
  listing: Listing,
  profit: ReturnType<typeof calculateResaleProfit>,
  options: { compCount: number; minProfit: number; minRoiPercent: number },
) {
  const warnings: string[] = [];
  const relevance = titleSimilarity(query, listing.title);
  if (isAccessoryMismatch(query, listing.title)) warnings.push("Looks like an accessory or part; reject unless that is intentional.");
  if (isModelTokenMismatch(query, listing.title)) warnings.push("Model token mismatch; verify exact variant before buying.");
  if (["craigslist", "facebook_marketplace", "offerup"].includes(listing.source)) {
    warnings.push("Local marketplace risk; verify seller identity, condition, and serial/authenticity.");
  }
  if (options.compCount < 4) warnings.push("Thin comp set; resale estimate is weak.");
  if (profit.net_profit < options.minProfit) warnings.push("Below requested minimum net profit.");
  if (profit.roi_percent < options.minRoiPercent) warnings.push("Below requested minimum ROI.");

  let riskScore = 25;
  if (["craigslist", "facebook_marketplace", "offerup"].includes(listing.source)) riskScore += 25;
  if (["unknown", "used"].includes(listing.condition)) riskScore += 10;
  if (relevance < 0.5) riskScore += 20;
  if (options.compCount < 4) riskScore += 15;
  riskScore = Math.min(riskScore, 100);
  const opportunityScore = (
    Math.min(Math.max(profit.roi_percent, 0), 100) * 0.45 +
    (Math.min(Math.max(profit.net_profit, 0), 250) / 250) * 35 +
    Math.max(0, 20 - riskScore * 0.2)
  );
  return {
    listing,
    net_profit: profit.net_profit,
    roi_percent: profit.roi_percent,
    max_buy_price_for_20_roi: profit.max_buy_price_for_20_roi,
    opportunity_score: roundMoney(opportunityScore),
    risk_score: riskScore,
    warnings,
  };
}

function draftEbayListing(args: {
  product_title: string;
  condition?: string;
  known_defects?: string;
  included_accessories?: string;
  comp_summary?: Record<string, unknown>;
}) {
  const condition = args.condition ?? "used";
  const suggestedPrice = args.comp_summary?.recommended_resale_price ?? args.comp_summary?.median_price ?? null;
  const bullets = [
    `Condition: ${condition.replace(/_/g, " ")}.`,
    "Tested and working unless otherwise noted.",
  ];
  if (args.included_accessories) bullets.push(`Includes: ${args.included_accessories}.`);
  if (args.known_defects) bullets.push(`Disclosure: ${args.known_defects}.`);
  else bullets.push("No known defects observed during inspection.");
  return {
    title: ebayListingTitle(args.product_title),
    suggested_price: typeof suggestedPrice === "number" ? suggestedPrice : null,
    format: "buy_it_now",
    condition,
    description: bullets.join("\n"),
    photo_checklist: [
      "Front, back, top, bottom, and ports",
      "Serial/model label if safe to show",
      "Screen/lens closeups",
      "Included accessories",
      "Any scratches, dents, missing parts, or defects",
    ],
    shipping_recommendation: "Use calculated shipping for heavy items; use buyer-paid or padded flat-rate only when dimensions are known.",
    disclosure_checklist: [
      "Confirm exact model number",
      "Confirm activation/account locks are removed where relevant",
      "Confirm battery health or runtime when relevant",
      "List missing accessories explicitly",
    ],
  };
}

async function saveResaleLead(env: Env, payload: Record<string, unknown>) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const now = new Date().toISOString();
  const lead = {
    id: typeof payload.id === "string" ? payload.id : `lead_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`,
    status: validLeadStatus(typeof payload.status === "string" ? payload.status : "watching"),
    created_at: now,
    updated_at: now,
    ...payload,
  };
  data.leads[String(lead.id)] = lead;
  await writeResaleData(env, data);
  return lead;
}

async function updateResaleLeadStatus(env: Env, leadId: string, status: string, notes?: string) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const lead = data.leads[leadId];
  if (!lead) return { error: `Unknown lead: ${leadId}` };
  lead.status = validLeadStatus(status);
  lead.updated_at = new Date().toISOString();
  if (notes) {
    const existingNotes = Array.isArray(lead.notes) ? lead.notes : [];
    lead.notes = [...existingNotes, { at: new Date().toISOString(), text: notes }];
  }
  await writeResaleData(env, data);
  return lead;
}

async function createInventoryItem(env: Env, payload: Record<string, unknown>) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const now = new Date().toISOString();
  const item = {
    id: typeof payload.id === "string" ? payload.id : `inv_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`,
    status: typeof payload.status === "string" ? payload.status : "purchased",
    created_at: now,
    updated_at: now,
    ...payload,
  };
  data.inventory[String(item.id)] = item;
  await writeResaleData(env, data);
  return item;
}

async function markInventoryListed(env: Env, inventoryId: string, listingUrl: string, askingPrice: number) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const item = data.inventory[inventoryId];
  if (!item) return { error: `Unknown inventory item: ${inventoryId}` };
  Object.assign(item, {
    status: "listed",
    listing_url: listingUrl,
    asking_price: askingPrice,
    listed_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
  await writeResaleData(env, data);
  return item;
}

async function markInventorySold(
  env: Env,
  args: {
    inventory_id: string;
    sale_price: number;
    sold_url?: string;
    outbound_shipping?: number;
    platform_fee_percent?: number;
  },
) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const item = data.inventory[args.inventory_id];
  if (!item) return { error: `Unknown inventory item: ${args.inventory_id}` };
  const profit = calculateResaleProfit(env, {
    purchase_price: numberValue(item.purchase_price),
    expected_sale_price: args.sale_price,
    inbound_shipping: numberValue(item.inbound_shipping),
    outbound_shipping: args.outbound_shipping ?? 0,
    purchase_tax_rate_percent: numberValue(item.purchase_tax_rate_percent),
    platform_fee_percent: args.platform_fee_percent,
  });
  Object.assign(item, {
    status: "sold",
    sale_price: args.sale_price,
    sold_url: args.sold_url ?? null,
    sold_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    profit,
  });
  await writeResaleData(env, data);
  return item;
}

async function calculateBusinessMetrics(env: Env) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const inventory = Object.values(data.inventory);
  const sold = inventory.filter((item) => item.status === "sold");
  const active = inventory.filter((item) => item.status !== "sold");
  const soldRevenue = sold.reduce((sum, item) => sum + numberValue(item.sale_price), 0);
  const realizedProfit = sold.reduce((sum, item) => sum + numberValue(objectValue(item.profit)?.net_profit), 0);
  const roiValues = sold.map((item) => numberValue(objectValue(item.profit)?.roi_percent)).filter((value) => value !== 0);
  return {
    lead_count: Object.keys(data.leads).length,
    vehicle_lead_count: Object.keys(data.vehicles).length,
    inventory_count: inventory.length,
    active_inventory_count: active.length,
    sold_count: sold.length,
    cash_invested_active: roundMoney(active.reduce((sum, item) => sum + numberValue(item.purchase_price), 0)),
    sold_revenue: roundMoney(soldRevenue),
    realized_net_profit: roundMoney(realizedProfit),
    average_realized_roi_percent: roiValues.length ? roundMoney(roiValues.reduce((a, b) => a + b, 0) / roiValues.length) : 0,
    leads_by_status: countByStatus(Object.values(data.leads)),
    vehicle_leads_by_status: countByStatus(Object.values(data.vehicles)),
    inventory_by_status: countByStatus(inventory),
  };
}

function decodeVin(vin: string) {
  const normalized = vin.trim().toUpperCase();
  const validFormat = /^[A-HJ-NPR-Z0-9]{17}$/.test(normalized);
  const expected = validFormat ? vinCheckDigit(normalized) : null;
  const actual = validFormat ? normalized[8] : null;
  return {
    vin: normalized,
    valid_format: validFormat,
    check_digit_valid: expected !== null ? expected === actual : null,
    check_digit_expected: expected,
    check_digit_actual: actual,
    wmi: validFormat ? normalized.slice(0, 3) : null,
    country: validFormat ? WMI_COUNTRIES[normalized[0] ?? ""] ?? null : null,
    model_year_code: validFormat ? normalized[9] : null,
    model_year_estimate: validFormat ? MODEL_YEAR_CODES[normalized[9] ?? ""] ?? null : null,
    plant_code: validFormat ? normalized[10] : null,
    serial: validFormat ? normalized.slice(11) : null,
    limitations: [
      "Offline VIN decoding only validates format/check digit and estimates year/country.",
      "Use an authoritative VIN/history provider for make, model, trim, title, accident, lien, and odometer data.",
    ],
  };
}

function calculateVehicleFlipProfit(args: {
  purchase_price: number;
  expected_sale_price: number;
  repair_cost?: number;
  transport_cost?: number;
  inspection_cost?: number;
  detail_cost?: number;
  title_registration_cost?: number;
  sales_tax_rate_percent?: number;
  storage_cost?: number;
  insurance_cost?: number;
  ebay_listing_fee?: number;
  deposit_amount?: number;
  misc_cost?: number;
}) {
  const repairCost = args.repair_cost ?? 0;
  const transportCost = args.transport_cost ?? 0;
  const inspectionCost = args.inspection_cost ?? 150;
  const detailCost = args.detail_cost ?? 150;
  const titleRegistrationCost = args.title_registration_cost ?? 450;
  const salesTaxRate = args.sales_tax_rate_percent ?? 0;
  const storageCost = args.storage_cost ?? 0;
  const insuranceCost = args.insurance_cost ?? 0;
  const listingFee = args.ebay_listing_fee ?? ebayMotorsListingFee(args.expected_sale_price);
  const depositProcessingFee = roundMoney((args.deposit_amount ?? 0) * 0.028);
  const miscCost = args.misc_cost ?? 0;
  const salesTax = roundMoney(args.purchase_price * (salesTaxRate / 100));
  const totalCost = roundMoney(
    args.purchase_price +
      salesTax +
      repairCost +
      transportCost +
      inspectionCost +
      detailCost +
      titleRegistrationCost +
      storageCost +
      insuranceCost +
      listingFee +
      depositProcessingFee +
      miscCost,
  );
  const netProfit = roundMoney(args.expected_sale_price - totalCost);
  const cashRequired = roundMoney(
    args.purchase_price +
      salesTax +
      repairCost +
      transportCost +
      inspectionCost +
      detailCost +
      titleRegistrationCost +
      storageCost +
      insuranceCost +
      miscCost,
  );
  return {
    purchase_price: roundMoney(args.purchase_price),
    expected_sale_price: roundMoney(args.expected_sale_price),
    sales_tax: salesTax,
    repair_cost: roundMoney(repairCost),
    transport_cost: roundMoney(transportCost),
    inspection_cost: roundMoney(inspectionCost),
    detail_cost: roundMoney(detailCost),
    title_registration_cost: roundMoney(titleRegistrationCost),
    storage_cost: roundMoney(storageCost),
    insurance_cost: roundMoney(insuranceCost),
    ebay_motors_listing_fee: roundMoney(listingFee),
    deposit_processing_fee: depositProcessingFee,
    total_cost: totalCost,
    net_profit: netProfit,
    roi_percent: cashRequired ? roundMoney((netProfit / cashRequired) * 100) : 0,
    break_even_sale_price: totalCost,
    max_buy_price_for_20_roi: maxVehicleBuyPriceForTarget({
      expectedSalePrice: args.expected_sale_price,
      targetRoiPercent: 20,
      repairCost,
      transportCost,
      inspectionCost,
      detailCost,
      titleRegistrationCost,
      salesTaxRatePercent: salesTaxRate,
      storageCost,
      insuranceCost,
      listingFee,
      depositProcessingFee,
      miscCost,
    }),
  };
}

function scoreVehicleTitleRisk(args: {
  title_status?: string;
  has_title_in_hand?: boolean | null;
  vin?: string;
  odometer_discrepancy?: boolean;
  seller_name_matches_title?: boolean | null;
  flood_risk_area?: boolean;
  lien_reported?: boolean;
}) {
  const warnings: string[] = [];
  const blockers: string[] = [];
  let score = 20;
  const titleStatus = (args.title_status ?? "unknown").trim().toLowerCase();
  if (["salvage", "rebuilt", "flood", "parts", "certificate_of_destruction"].includes(titleStatus)) {
    score += 35;
    warnings.push("Non-clean title status; resale market and buyer financing may be limited.");
  } else if (!titleStatus || titleStatus === "unknown") {
    score += 25;
    warnings.push("Title status is unknown.");
  }
  if (args.has_title_in_hand === false) {
    score += 35;
    blockers.push("Seller does not have title in hand.");
  } else if (args.has_title_in_hand === undefined || args.has_title_in_hand === null) {
    score += 15;
    warnings.push("Title-in-hand status is unknown.");
  }
  if (args.seller_name_matches_title === false) {
    score += 30;
    blockers.push("Seller name does not match title.");
  } else if (args.seller_name_matches_title === undefined || args.seller_name_matches_title === null) {
    score += 10;
    warnings.push("Seller/title name match is unknown.");
  }
  if (args.vin) {
    const decoded = decodeVin(args.vin);
    if (!decoded.valid_format || decoded.check_digit_valid === false) {
      score += 30;
      blockers.push("VIN failed basic validation.");
    }
  } else {
    score += 15;
    warnings.push("VIN is missing.");
  }
  if (args.odometer_discrepancy) {
    score += 35;
    blockers.push("Odometer discrepancy reported.");
  }
  if (args.lien_reported) {
    score += 35;
    blockers.push("Lien reported; payoff/release must be verified before purchase.");
  }
  if (args.flood_risk_area ?? true) {
    score += 10;
    warnings.push("Flood-risk market; inspect for water intrusion and title branding.");
  }
  score = Math.min(score, 100);
  return {
    risk_score: score,
    risk_level: riskLevel(score),
    blockers,
    warnings,
    required_checks: [
      "Confirm physical title is present before payment.",
      "Confirm VIN on dash, door jamb, and title match.",
      "Run vehicle history report.",
      "Check for liens, salvage/rebuilt/flood branding, and odometer anomalies.",
      "Use pre-purchase inspection or mobile mechanic before committing.",
    ],
  };
}

function floridaDealerThresholdStatus(args: {
  vehicles_sold_or_offered_12mo: number;
  planned_new_vehicle_offers?: number;
}) {
  const planned = args.planned_new_vehicle_offers ?? 1;
  const projected = args.vehicles_sold_or_offered_12mo + planned;
  return {
    jurisdiction: "Florida",
    vehicles_sold_or_offered_12mo: args.vehicles_sold_or_offered_12mo,
    planned_new_vehicle_offers: planned,
    projected_12mo_count: projected,
    dealer_presumption_threshold: FLORIDA_DEALER_PRESUMPTION_THRESHOLD,
    remaining_before_threshold: Math.max(FLORIDA_DEALER_PRESUMPTION_THRESHOLD - args.vehicles_sold_or_offered_12mo, 0),
    likely_dealer_activity_presumption: projected >= FLORIDA_DEALER_PRESUMPTION_THRESHOLD,
    note: "Florida law creates a prima facie presumption of dealer activity at three or more motor vehicles bought, sold, dealt, offered, or displayed for sale in 12 months.",
  };
}

function buildVehicleMarketComps(query: string, listings: Listing[], maxComps: number) {
  return {
    ...buildResaleComps(query, listings, maxComps),
    basis: "active_ebay_motors_listing_proxy",
    limitation: "Uses active eBay listing data as a market proxy. Confirm sold/auction results, trim, mileage, title status, accident history, and location before buying.",
  };
}

function scoreVehicleOpportunity(
  query: string,
  listing: Listing,
  profit: ReturnType<typeof calculateVehicleFlipProfit>,
  options: {
    compCount: number;
    minProfit: number;
    minRoiPercent: number;
    titleRisk: ReturnType<typeof scoreVehicleTitleRisk>;
    dealerThreshold: ReturnType<typeof floridaDealerThresholdStatus>;
  },
) {
  const warnings: string[] = [];
  const blockers = [...options.titleRisk.blockers];
  const relevance = titleSimilarity(query, listing.title);
  if (options.compCount < 4) warnings.push("Thin vehicle comp set; resale estimate is weak.");
  if (profit.net_profit < options.minProfit) warnings.push("Below requested minimum net profit.");
  if (profit.roi_percent < options.minRoiPercent) warnings.push("Below requested minimum ROI.");
  if (relevance < 0.45) warnings.push("Weak title match; verify year/make/model/trim manually.");
  if (options.dealerThreshold.likely_dealer_activity_presumption) warnings.push("Projected Florida activity may trigger dealer-license presumption.");
  if (["facebook_marketplace", "craigslist", "offerup"].includes(listing.source)) warnings.push("Private/local seller; verify title, VIN, liens, and seller identity.");
  const riskScore = Math.min(100, options.titleRisk.risk_score + (options.compCount < 4 ? 20 : 0) + (relevance < 0.45 ? 10 : 0));
  let opportunityScore = (
    Math.min(Math.max(profit.roi_percent, 0), 100) * 0.35 +
    (Math.min(Math.max(profit.net_profit, 0), 5000) / 5000) * 45 +
    Math.max(0, 20 - riskScore * 0.2)
  );
  if (blockers.length) opportunityScore = Math.min(opportunityScore, 35);
  return {
    listing,
    net_profit: profit.net_profit,
    roi_percent: profit.roi_percent,
    max_buy_price_for_20_roi: profit.max_buy_price_for_20_roi,
    opportunity_score: roundMoney(opportunityScore),
    risk_score: riskScore,
    risk_level: riskLevel(riskScore),
    warnings: [...warnings, ...options.titleRisk.warnings],
    blockers,
    dealer_threshold: options.dealerThreshold,
  };
}

function draftEbayMotorsListing(args: {
  year?: number;
  make?: string;
  model?: string;
  trim?: string;
  mileage?: number;
  title_status?: string;
  known_issues?: string;
  recent_service?: string;
}) {
  const title = [args.year ? String(args.year) : "", args.make ?? "", args.model ?? "", args.trim ?? ""].filter((part) => part.trim()).join(" ");
  const details = [
    `Title status: ${args.title_status ?? "clean"}.`,
    args.mileage !== undefined ? `Mileage: ${args.mileage.toLocaleString()}.` : "Mileage: verify from odometer photo.",
    "VIN should be provided to serious buyers after screening.",
  ];
  if (args.recent_service) details.push(`Recent service: ${args.recent_service}.`);
  if (args.known_issues) details.push(`Known issues: ${args.known_issues}.`);
  else details.push("Known issues: none disclosed; buyer inspection welcome.");
  return {
    title: title.slice(0, 80),
    format: "fixed_price_or_auction_with_reserve",
    description: details.join("\n"),
    photo_checklist: [
      "Exterior all four corners",
      "Interior front/rear seats",
      "Dashboard with mileage visible",
      "VIN plate and door jamb sticker",
      "Engine bay",
      "Tires and wheels",
      "Undercarriage/rust areas",
      "Any damage, warning lights, leaks, or wear",
      "Title with sensitive info covered",
    ],
    required_disclosures: [
      "Title brand/status",
      "Known mechanical issues",
      "Accident/flood history if known",
      "Odometer accuracy",
      "Lien/payoff status",
      "Pickup/payment terms",
    ],
    fee_note: "eBay Motors vehicle listings use listing-package fees rather than normal item final value fees.",
  };
}

async function saveVehicleLead(env: Env, payload: Record<string, unknown>) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const now = new Date().toISOString();
  const vehicle = {
    id: typeof payload.id === "string" ? payload.id : `veh_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`,
    status: typeof payload.status === "string" ? payload.status : "researching",
    created_at: now,
    updated_at: now,
    ...payload,
  };
  data.vehicles[String(vehicle.id)] = vehicle;
  await writeResaleData(env, data);
  return vehicle;
}

async function updateVehicleStatus(env: Env, vehicleId: string, status: string, notes?: string) {
  const data = await readResaleData(env);
  if ("error" in data) return data;
  const vehicle = data.vehicles[vehicleId];
  if (!vehicle) return { error: `Unknown vehicle lead: ${vehicleId}` };
  vehicle.status = status;
  vehicle.updated_at = new Date().toISOString();
  if (notes) {
    const existingNotes = Array.isArray(vehicle.notes) ? vehicle.notes : [];
    vehicle.notes = [...existingNotes, { at: new Date().toISOString(), text: notes }];
  }
  await writeResaleData(env, data);
  return vehicle;
}

async function readResaleData(env: Env): Promise<ResaleData | { error: string; requires: string[] }> {
  if (!env.RESALE_KV) {
    return {
      error: "Resale persistence is not configured for this Worker.",
      requires: ["Bind a Cloudflare KV namespace as RESALE_KV"],
    };
  }
  const stored = await env.RESALE_KV.get("resale-business", "json") as ResaleData | null;
  return { leads: {}, inventory: {}, vehicles: {}, ...(stored ?? {}) };
}

async function writeResaleData(env: Env, data: ResaleData): Promise<void> {
  if (!env.RESALE_KV) throw new Error("RESALE_KV is not configured.");
  await env.RESALE_KV.put("resale-business", JSON.stringify(data));
}

function dedupeListings(listings: Listing[]): Listing[] {
  const seenUrls = new Set<string>();
  const byTitle = new Map<string, Listing>();
  for (const listing of listings) {
    const urlKey = listing.url.split("?")[0]?.replace(/\/$/, "").toLowerCase();
    if (seenUrls.has(urlKey)) continue;
    seenUrls.add(urlKey);
    const key = `${listing.source}:${normalizeText(listing.title)}`;
    const existing = byTitle.get(key);
    if (!existing || priceSort(listing) < priceSort(existing)) byTitle.set(key, listing);
  }
  return [...byTitle.values()];
}

function ebayQueryVariants(query: string): string[] {
  const normalized = normalizeText(query);
  const variants = [query];
  if (normalized.includes("pocket") && (normalized.includes("4p") || normalized.includes("four pro"))) {
    variants.push(
      "DJI Osmo Pocket 4P",
      "Osmo Pocket 4P",
      "DJI Osmo Pocket Four Pro",
      "Osmo Pocket Four Pro",
      "DJI Osmo Pocket 4P Standard Combo",
      "DJI Osmo Pocket 4P Vlog Combo",
    );
  }
  return [...new Set(variants)];
}

function isAccessoryMismatch(query: string, title: string): boolean {
  const queryTokens = new Set(normalizeText(query).split(/\s+/).filter(Boolean));
  const titleText = normalizeText(title);
  const titleTokens = new Set(titleText.split(/\s+/).filter(Boolean));
  const hits = [...titleTokens].filter((token) => ACCESSORY_TERMS.has(token));
  const compatible = titleText.includes("compatible with") || titleText.includes("for ");
  return hits.length > 0 && (compatible || hits.some((token) => !queryTokens.has(token)));
}

function isModelTokenMismatch(query: string, title: string): boolean {
  const queryIphoneModel = phoneModelNumber(query, "iphone");
  const titleIphoneModel = phoneModelNumber(title, "iphone");
  if (queryIphoneModel && titleIphoneModel && queryIphoneModel !== titleIphoneModel) return true;

  const queryTokens = normalizeText(query).split(/\s+/).filter(Boolean);
  const titleTokens = new Set(normalizeText(title).split(/\s+/).filter(Boolean));
  return queryTokens.some((token) => /\d/.test(token) && token.length >= 2 && !titleTokens.has(token));
}

function phoneModelNumber(text: string, family: string): string | null {
  const found = normalizeText(text).match(new RegExp(`\\b${family}\\s+(\\d{1,2})\\b`));
  return found?.[1] ?? null;
}

function titleSimilarity(query: string, title: string): number {
  const queryTokens = normalizeText(query).split(/\s+/).filter(Boolean);
  const titleTokens = new Set(normalizeText(title).split(/\s+/).filter(Boolean));
  if (!queryTokens.length) return 0;
  return queryTokens.filter((token) => titleTokens.has(token)).length / queryTokens.length;
}

function rankReason(listing: Listing, low: number | null, avg: number | null, relevance: number): string {
  const pieces: string[] = [];
  const price = effectivePrice(listing);
  const basis = listing.total_with_tax !== null && listing.total_with_tax !== undefined
    ? "estimated total with tax"
    : listing.total_price !== null && listing.total_price !== undefined ? "shipped total" : "price";
  if (price !== null && low !== null && price === low) pieces.push(`lowest observed ${basis}`);
  else if (price !== null && avg !== null && price < avg) pieces.push(`below the observed average ${basis} of $${avg.toFixed(2)}`);
  else if (price !== null) pieces.push(`${basis} within the observed result range`);
  else pieces.push("price unavailable");
  pieces.push(relevance >= 0.75 ? "strong title match" : relevance >= 0.45 ? "reasonable title match" : "weak title match");
  if (listing.condition && listing.condition !== "unknown") pieces.push(`condition: ${listing.condition}`);
  return pieces.join("; ");
}

function normalizeText(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").trim();
}

function productKey(title: string): string {
  const stop = new Set(["the", "a", "an", "for", "with", "and", "or", "new", "used", "open", "box"]);
  return normalizeText(title).split(/\s+/).filter((token) => token.length > 1 && !stop.has(token)).slice(0, 8).join(" ");
}

function medianNumber(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const midpoint = Math.floor(sorted.length / 2);
  if (sorted.length % 2) return roundMoney(sorted[midpoint] ?? 0);
  return roundMoney(((sorted[midpoint - 1] ?? 0) + (sorted[midpoint] ?? 0)) / 2);
}

function recommendedResalePrice(prices: number[]): number | null {
  if (!prices.length) return null;
  const sorted = [...prices].sort((a, b) => a - b);
  const trimmed = sorted.length >= 4 ? sorted.slice(1, -1) : sorted;
  return medianNumber(trimmed);
}

function sellThroughConfidence(compCount: number, prices: number[]): string {
  if (compCount >= 15 && coefficientOfVariation(prices) < 0.35) return "medium";
  if (compCount >= 6) return "low_medium";
  if (compCount > 0) return "low";
  return "unknown";
}

function coefficientOfVariation(prices: number[]): number {
  if (prices.length < 2) return 1;
  const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
  if (!avg) return 1;
  const variance = prices.reduce((sum, price) => sum + (price - avg) ** 2, 0) / prices.length;
  return Math.sqrt(variance) / avg;
}

function ebayListingTitle(title: string): string {
  const words = title.replace(/\s+/g, " ").trim().split(/\s+/);
  const output: string[] = [];
  let length = 0;
  for (const word of words) {
    const nextLength = length + word.length + (output.length ? 1 : 0);
    if (nextLength > 80) break;
    output.push(word);
    length = nextLength;
  }
  return output.join(" ");
}

function validLeadStatus(status: string): string {
  if (!LEAD_STATUSES.has(status)) {
    throw new Error(`Status must be one of: ${[...LEAD_STATUSES].sort().join(", ")}`);
  }
  return status;
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function countByStatus(items: Record<string, unknown>[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    const status = typeof item.status === "string" ? item.status : "unknown";
    counts[status] = (counts[status] ?? 0) + 1;
  }
  return counts;
}

function ebayMotorsListingFee(expectedSalePrice: number): number {
  return expectedSalePrice > EBAY_MOTORS_HIGH_PRICE_THRESHOLD
    ? EBAY_MOTORS_HIGH_LISTING_FEE
    : EBAY_MOTORS_LOW_LISTING_FEE;
}

function maxVehicleBuyPriceForTarget(args: {
  expectedSalePrice: number;
  targetRoiPercent: number;
  repairCost: number;
  transportCost: number;
  inspectionCost: number;
  detailCost: number;
  titleRegistrationCost: number;
  salesTaxRatePercent: number;
  storageCost: number;
  insuranceCost: number;
  listingFee: number;
  depositProcessingFee: number;
  miscCost: number;
}): number {
  const fixedCosts = args.repairCost +
    args.transportCost +
    args.inspectionCost +
    args.detailCost +
    args.titleRegistrationCost +
    args.storageCost +
    args.insuranceCost +
    args.listingFee +
    args.depositProcessingFee +
    args.miscCost;
  const denominator = 1 + args.salesTaxRatePercent / 100 + args.targetRoiPercent / 100;
  return roundMoney(Math.max((args.expectedSalePrice - fixedCosts) / denominator, 0));
}

function vinCheckDigit(vin: string): string | null {
  if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) return null;
  const total = [...vin].reduce((sum, char, index) =>
    sum + (VIN_TRANSLITERATION[char] ?? 0) * (VIN_WEIGHTS[index] ?? 0), 0);
  const remainder = total % 11;
  return remainder === 10 ? "X" : String(remainder);
}

function riskLevel(score: number): string {
  if (score >= 80) return "very_high";
  if (score >= 60) return "high";
  if (score >= 40) return "medium";
  return "low";
}

function parsePrice(value: unknown): number | null {
  if (typeof value === "number") return value >= 0 ? value : null;
  if (value === null || value === undefined) return null;
  const match = String(value).replace(/,/g, "").match(/\$?\s*([0-9]+(?:\.[0-9]{2})?)/);
  return match ? Number(match[1]) : null;
}

function amount(payload: Record<string, unknown> | null): number | null {
  return parsePrice(payload?.value);
}

function normalizeCondition(value: unknown): string {
  const text = String(value ?? "unknown").toLowerCase();
  if (text.includes("certified") || text.includes("refurb")) return "refurbished";
  if (text.includes("open")) return "open_box";
  if (text.includes("used") || text.includes("pre-owned")) return "used";
  if (text.includes("new")) return "new";
  return "unknown";
}

function locationText(payload: Record<string, unknown> | null): string | null {
  if (!payload) return null;
  const parts = [payload.city, payload.stateOrProvince, payload.country, payload.postalCode].filter(Boolean).map(String);
  return parts.length ? parts.join(", ") : null;
}

function craigslistAddress(site: string, payload: Record<string, unknown> | null): string {
  if (!payload) return site;
  const parts = [payload.addressLocality, payload.addressRegion].filter(Boolean).map(String);
  return parts.length ? `${site}: ${parts.join(", ")}` : site;
}

function shippingText(item: Record<string, unknown>): string | null {
  const cost = ebayShippingCost(item);
  if (cost === 0) return "Free shipping";
  if (cost !== null) return `Shipping $${cost.toFixed(2)}`;
  const options = Array.isArray(item.shippingOptions) ? item.shippingOptions : [];
  const first = objectValue(options[0]);
  return typeof first?.shippingCostType === "string" ? first.shippingCostType : null;
}

function ebayShippingCost(item: Record<string, unknown>): number | null {
  const options = Array.isArray(item.shippingOptions) ? item.shippingOptions : [];
  const first = objectValue(options[0]);
  return amount(objectValue(first?.shippingCost));
}

function facebookListingPrice(item: Record<string, unknown>): number | null {
  const listingPrice = objectValue(item.listing_price);
  const amountValue = parsePrice(listingPrice?.amount);
  if (amountValue !== null) return amountValue / 100;
  return parsePrice(listingPrice?.formatted_amount ?? item.price ?? item.currentPrice);
}

function facebookListingImage(item: Record<string, unknown>): string | null {
  const photo = objectValue(item.primary_listing_photo);
  const image = objectValue(photo?.image);
  if (typeof image?.uri === "string") return image.uri;
  if (typeof photo?.uri === "string") return photo.uri;
  return null;
}

function facebookListingLocation(item: Record<string, unknown>): string | null {
  const location = objectValue(item.location);
  const reverse = objectValue(location?.reverse_geocode);
  const reverseCity = objectValue(reverse?.city_page);
  const city = objectValue(location?.city_page);
  if (typeof reverseCity?.display_name === "string") return reverseCity.display_name;
  if (typeof city?.display_name === "string") return city.display_name;
  return typeof location?.single_line_address === "string" ? location.single_line_address : null;
}

function facebookCoordinates(env: Env, location?: string): { latitude: number; longitude: number } | null {
  if (location) {
    const found = location.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (found) return { latitude: Number(found[1]), longitude: Number(found[2]) };
    const city = cityCoordinates(location);
    if (city) return city;
  }
  const latitude = Number.parseFloat(env.SHOPPING_FACEBOOK_MARKETPLACE_LATITUDE ?? "");
  const longitude = Number.parseFloat(env.SHOPPING_FACEBOOK_MARKETPLACE_LONGITUDE ?? "");
  if (Number.isFinite(latitude) && Number.isFinite(longitude)) return { latitude, longitude };
  return null;
}

function cityCoordinates(location: string): { latitude: number; longitude: number } | null {
  const normalized = location.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const aliases: Record<string, { latitude: number; longitude: number }> = {
    atlanta: { latitude: 33.7490, longitude: -84.3880 },
    austin: { latitude: 30.2672, longitude: -97.7431 },
    boston: { latitude: 42.3601, longitude: -71.0589 },
    chicago: { latitude: 41.8781, longitude: -87.6298 },
    dallas: { latitude: 32.7767, longitude: -96.7970 },
    denver: { latitude: 39.7392, longitude: -104.9903 },
    houston: { latitude: 29.7604, longitude: -95.3698 },
    "las vegas": { latitude: 36.1716, longitude: -115.1391 },
    "los angeles": { latitude: 34.0522, longitude: -118.2437 },
    miami: { latitude: 25.7617, longitude: -80.1918 },
    "new orleans": { latitude: 29.9511, longitude: -90.0715 },
    "new york": { latitude: 40.7128, longitude: -74.0060 },
    "new york city": { latitude: 40.7128, longitude: -74.0060 },
    nyc: { latitude: 40.7128, longitude: -74.0060 },
    philadelphia: { latitude: 39.9526, longitude: -75.1652 },
    phoenix: { latitude: 33.4484, longitude: -112.0740 },
    portland: { latitude: 45.5152, longitude: -122.6784 },
    "san antonio": { latitude: 29.4252, longitude: -98.4946 },
    "san diego": { latitude: 32.7157, longitude: -117.1611 },
    "san francisco": { latitude: 37.7749, longitude: -122.4194 },
    sfbay: { latitude: 37.7749, longitude: -122.4194 },
    seattle: { latitude: 47.6062, longitude: -122.3321 },
    "washington dc": { latitude: 38.9072, longitude: -77.0369 },
  };
  return aliases[normalized] ?? null;
}

function extractFacebookLsdToken(html: string): string {
  return match(html, /"LSD",\[\],\{"token":"([^"]+)"/) ||
    match(html, /name="lsd"\s+value="([^"]+)"/) ||
    match(html, /"lsd"\s*:\s*"([^"]+)"/);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? value as Record<string, unknown> : null;
}

function ebayBrowseBase(env: Env): string {
  return boolEnv(env.EBAY_USE_SANDBOX, false) ? "https://api.sandbox.ebay.com/buy/browse/v1" : "https://api.ebay.com/buy/browse/v1";
}

function ebayOauthUrl(env: Env): string {
  return boolEnv(env.EBAY_USE_SANDBOX, false) ? "https://api.sandbox.ebay.com/identity/v1/oauth2/token" : "https://api.ebay.com/identity/v1/oauth2/token";
}

function ebayCandidateSort(query: string, a: Listing, b: Listing): number {
  return Number(isAccessoryMismatch(query, a.title)) - Number(isAccessoryMismatch(query, b.title)) ||
    Number(isModelTokenMismatch(query, a.title)) - Number(isModelTokenMismatch(query, b.title)) ||
    priceSort(a) - priceSort(b) ||
    a.title.localeCompare(b.title);
}

function searchResultSort(query: string, a: Listing, b: Listing): number {
  return Number(isAccessoryMismatch(query, a.title)) - Number(isAccessoryMismatch(query, b.title)) ||
    Number(isModelTokenMismatch(query, a.title)) - Number(isModelTokenMismatch(query, b.title)) ||
    titleSimilarity(query, b.title) - titleSimilarity(query, a.title) ||
    priceSort(a) - priceSort(b) ||
    a.title.localeCompare(b.title);
}

function priceSort(listing: Listing): number {
  return priceSortValue(effectivePrice(listing));
}

function priceSortValue(price: number | null): number {
  return price === null ? Number.POSITIVE_INFINITY : price;
}

function effectivePrice(listing: Listing): number | null {
  if (listing.total_with_tax !== undefined && listing.total_with_tax !== null) return listing.total_with_tax;
  return listing.total_price ?? listing.price;
}

function totalPrice(price: number | null, shippingCost: number | null): number | null {
  if (price === null) return null;
  return price + (shippingCost ?? 0);
}

function applyTaxEstimates(
  env: Env,
  listings: Listing[],
  taxRatePercent?: number,
  taxOnShipping?: boolean,
): Listing[] {
  const rate = resolvedTaxRate(env, taxRatePercent);
  if (rate === null) return listings;
  const includeShipping = resolvedTaxOnShipping(env, taxOnShipping);
  return listings.map((listing) => {
    const baseTotal = listing.total_price ?? listing.price;
    if (baseTotal === null || listing.price === null) return listing;
    const taxableBase = includeShipping ? baseTotal : listing.price;
    const estimatedTax = roundMoney(taxableBase * (rate / 100));
    return {
      ...listing,
      estimated_tax: estimatedTax,
      total_with_tax: roundMoney(baseTotal + estimatedTax),
    };
  });
}

function resolvedTaxRate(env: Env, taxRatePercent?: number): number | null {
  if (taxRatePercent !== undefined) return taxRatePercent;
  const parsed = Number.parseFloat(env.SHOPPING_ESTIMATED_TAX_RATE_PERCENT ?? "");
  return Number.isFinite(parsed) ? parsed : null;
}

function resolvedTaxOnShipping(env: Env, taxOnShipping?: boolean): boolean {
  if (taxOnShipping !== undefined) return taxOnShipping;
  return boolEnv(env.SHOPPING_TAX_SHIPPING, true);
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function applyPriceBounds(listings: Listing[], priceMin?: number, priceMax?: number): Listing[] {
  return listings.filter((listing) =>
    (listing.price === null || priceMin === undefined || listing.price >= priceMin) &&
    (listing.price === null || priceMax === undefined || listing.price <= priceMax),
  );
}

function cleanAmazonTitle(value: string): string {
  return value
    .replace(/^Sponsored Sponsored You(?:'|’)re seeing this ad based on the product(?:'|’)s relevance to your search query\. Leave ad feedback\s+/i, "")
    .trim();
}

function collectOfferUpListings(obj: unknown, results: Record<string, unknown>[]): void {
  if (Array.isArray(obj)) {
    for (const value of obj) collectOfferUpListings(value, results);
    return;
  }
  if (!obj || typeof obj !== "object") return;
  const record = obj as Record<string, unknown>;
  if (record.__typename === "ModularFeedListing" && record.title) results.push(record);
  for (const value of Object.values(record)) collectOfferUpListings(value, results);
}

function browserHeaders(accept: string): HeadersInit {
  return {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept": accept,
    "Accept-Language": "en-US,en;q=0.9",
  };
}

function facebookHeaders(): Record<string, string> {
  return {
    "User-Agent": FACEBOOK_MOBILE_USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
  };
}

async function timedFetch(env: Env, input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const timeout = intEnv(env.SHOPPING_HTTP_TIMEOUT_SECONDS, 15) * 1000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), timeout);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function craigslistSites(env: Env): string[] {
  return (env.CRAIGSLIST_SITES ?? "newyork,sfbay,losangeles,chicago,houston").split(",").map((site) => site.trim()).filter(Boolean);
}

function intEnv(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function boolEnv(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined) return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function match(text: string, pattern: RegExp): string {
  return text.match(pattern)?.[1] ?? "";
}

function stripTags(value: string): string {
  return value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

function cdata(value: string): string {
  return value.replace(/^<!\[CDATA\[/, "").replace(/\]\]>$/, "");
}

function decodeHtml(value: string): string {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}
