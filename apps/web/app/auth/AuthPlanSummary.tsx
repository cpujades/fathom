"use client";

import { resolveAuthPlanSummary } from "../content/pricing";
import { formatPricingPrice } from "../lib/pricingCurrency";
import { usePricingCurrency } from "../lib/usePricingCurrency";
import styles from "./auth.module.css";

type AuthPlanSummaryProps = {
  intent: string | null;
  plan: string | null;
};

export function AuthPlanSummary({ intent, plan }: AuthPlanSummaryProps) {
  const { currency } = usePricingCurrency();
  const selection = resolveAuthPlanSummary(intent, plan);
  if (!selection) {
    return null;
  }

  return (
    <section className={styles.planSummary} aria-labelledby="auth-plan-summary-title">
      <h3 className={styles.planSummaryTitle} id="auth-plan-summary-title">
        Continue with {selection.productName}
      </h3>
      <p className={styles.planSummaryDetails}>
        {formatPricingPrice(selection.prices, currency)} {selection.paymentCadence} · {selection.includedTime}
      </p>
    </section>
  );
}
