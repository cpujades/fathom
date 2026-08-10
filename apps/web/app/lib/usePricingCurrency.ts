"use client";

import { useCallback, useEffect, useState } from "react";

import type { PricingCurrency } from "../content/pricing";
import {
  DEFAULT_PRICING_CURRENCY,
  PRICING_CURRENCY_STORAGE_KEY,
  isPricingCurrency,
  resolveLocalePricingCurrency
} from "./pricingCurrency";

const usePricingCurrency = () => {
  const [currency, setCurrency] = useState<PricingCurrency>(DEFAULT_PRICING_CURRENCY);

  useEffect(() => {
    let storedCurrency: string | null = null;
    try {
      storedCurrency = window.localStorage.getItem(PRICING_CURRENCY_STORAGE_KEY);
    } catch {
      // Storage can be unavailable in privacy-restricted browsers.
    }

    if (isPricingCurrency(storedCurrency)) {
      setCurrency(storedCurrency);
      return;
    }

    setCurrency(resolveLocalePricingCurrency(navigator.language));
  }, []);

  const selectCurrency = useCallback((nextCurrency: PricingCurrency) => {
    setCurrency(nextCurrency);
    try {
      window.localStorage.setItem(PRICING_CURRENCY_STORAGE_KEY, nextCurrency);
    } catch {
      // The display preference is optional; pricing remains usable without storage.
    }
  }, []);

  return { currency, selectCurrency };
};

export { usePricingCurrency };
