import type { PricingCurrency, PricingPrices } from "../content/pricing";

const DEFAULT_PRICING_CURRENCY: PricingCurrency = "usd";
const PRICING_CURRENCY_STORAGE_KEY = "talven-pricing-currency";
const EUR_REGIONS = new Set([
  "AD",
  "AT",
  "AX",
  "BE",
  "BG",
  "BL",
  "CY",
  "DE",
  "EE",
  "ES",
  "FI",
  "FR",
  "GF",
  "GP",
  "GR",
  "HR",
  "IE",
  "IT",
  "LT",
  "LU",
  "LV",
  "MC",
  "ME",
  "MF",
  "MQ",
  "MT",
  "NL",
  "PM",
  "PT",
  "RE",
  "SI",
  "SK",
  "SM",
  "TF",
  "VA",
  "XK",
  "YT"
]);
const GBP_REGIONS = new Set(["GB", "GG", "IM", "JE"]);

const isPricingCurrency = (value: unknown): value is PricingCurrency =>
  value === "eur" || value === "usd" || value === "gbp";

const resolveLocalePricingCurrency = (locale: string): PricingCurrency => {
  try {
    const region = new Intl.Locale(locale).maximize().region;
    if (!region) {
      return DEFAULT_PRICING_CURRENCY;
    }

    if (EUR_REGIONS.has(region)) {
      return "eur";
    }
    if (GBP_REGIONS.has(region)) {
      return "gbp";
    }
    return DEFAULT_PRICING_CURRENCY;
  } catch {
    return DEFAULT_PRICING_CURRENCY;
  }
};

const formatPricingAmount = (amountCents: number, currency: PricingCurrency): string => {
  if (amountCents === 0) {
    return "Free";
  }

  const hasFraction = amountCents % 100 !== 0;
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0
  }).format(amountCents / 100);
};

const formatPricingPrice = (prices: PricingPrices, currency: PricingCurrency): string =>
  formatPricingAmount(prices[currency], currency);

const formatPricingPlanPrice = (
  prices: PricingPrices,
  currency: PricingCurrency,
  billingInterval: string | null
): string => {
  if (prices[currency] <= 0) {
    return "Free";
  }

  const price = formatPricingPrice(prices, currency);
  return billingInterval ? `${price}/${billingInterval}` : price;
};

export {
  DEFAULT_PRICING_CURRENCY,
  PRICING_CURRENCY_STORAGE_KEY,
  formatPricingPlanPrice,
  formatPricingPrice,
  isPricingCurrency,
  resolveLocalePricingCurrency
};
