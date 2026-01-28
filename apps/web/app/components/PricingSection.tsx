"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

import styles from "../page.module.css";
import { packPlans, pricingCopy, subscriptionPlans } from "../content/pricing";

export default function PricingSection({ className }: { className?: string }) {
  const [mode, setMode] = useState<"packs" | "subscriptions">("packs");

  const plans = useMemo(() => {
    return mode === "packs" ? packPlans : subscriptionPlans;
  }, [mode]);

  const copy = pricingCopy[mode];

  return (
    <section className={className} id="pricing">
      <div className={styles.pricingHeaderRow}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>{copy.headline}</h2>
          <p className={styles.sectionText}>{copy.subhead}</p>
          {copy.benefits ? (
            <div className={styles.pricingBenefits}>
              {copy.benefits.map((benefit) => (
                <div key={benefit} className={styles.pricingBenefit}>
                  {benefit}
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div className={styles.toggle} role="group" aria-label="Pricing mode">
          <button
            className={`${styles.toggleButton} ${
              mode === "packs" ? styles.toggleButtonActive : ""
            }`}
            onClick={() => setMode("packs")}
            type="button"
          >
            Packs
          </button>
          <button
            className={`${styles.toggleButton} ${
              mode === "subscriptions" ? styles.toggleButtonActive : ""
            }`}
            onClick={() => setMode("subscriptions")}
            type="button"
          >
            Subscriptions
          </button>
        </div>
      </div>

      <div className={styles.pricing}>
        {plans.map((plan) => (
          <div
            key={`${mode}-${plan.name}`}
            className={`${styles.priceCard} ${plan.highlight ? styles.priceCardHighlight : ""}`}
          >
            <div className={`${styles.pill} ${styles.pillSpaced}`}>{plan.tag}</div>
            <h3 className={styles.cardTitle}>{plan.name}</h3>
            <p className={styles.priceTag}>{plan.price}</p>
            <div className={styles.priceMeta}>{plan.hours}</div>
            <div className={styles.priceList}>
              {plan.features.map((feature) => (
                <div key={feature}>- {feature}</div>
              ))}
            </div>
            <Link className={`${styles.button} ${styles.buttonGhost} ${styles.priceCta}`} href="/signup">
              {mode === "packs" ? `Buy ${plan.name} pack` : `Choose ${plan.name}`}
            </Link>
          </div>
        ))}
      </div>

      <div className={styles.priceFootnote}>
        {copy.footnote}
        {copy.footnoteMuted ? (
          <span className={styles.priceFootnoteMuted}>{copy.footnoteMuted}</span>
        ) : null}
      </div>
    </section>
  );
}
