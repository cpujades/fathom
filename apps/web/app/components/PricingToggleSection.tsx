"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { type KeyboardEvent, useEffect, useState } from "react";

import { packPlans, pricingCopy, subscriptionPlans } from "../content/pricing";
import { trackMarketingEvent } from "../lib/marketingEvents";
import { formatPricingPrice } from "../lib/pricingCurrency";
import { buildPaidCheckoutHref } from "../lib/pricingIntent";
import { usePricingCurrency } from "../lib/usePricingCurrency";
import { PricingCurrencySelect } from "./PricingCurrencySelect";
import styles from "./pricing-toggle-section.module.css";

type BillingMode = "subscriptions" | "packs";

type PricingToggleSectionProps = {
  mode: BillingMode;
};

export default function PricingToggleSection({ mode }: PricingToggleSectionProps) {
  const shouldReduceMotion = useReducedMotion();
  const [activeMode, setActiveMode] = useState<BillingMode>(mode);
  const { currency, selectCurrency } = usePricingCurrency();

  useEffect(() => {
    setActiveMode(mode);
  }, [mode]);

  const plans = activeMode === "subscriptions" ? subscriptionPlans : packPlans;
  const highlightedPlan = plans.find((plan) => plan.highlight) ?? plans[0];
  const copy = pricingCopy[activeMode];
  const stageTransition = shouldReduceMotion
    ? { duration: 0 }
    : { duration: 0.22, ease: [0.22, 1, 0.36, 1] as const };
  const trackPricingCtaClick = (ctaName: "card" | "secondary", planName?: string) => {
    trackMarketingEvent({
      event: "pricing_plan_cta_clicked",
      section: "pricing",
      cta: ctaName,
      mode: activeMode,
      plan: planName ?? highlightedPlan?.planCode ?? "starter"
    });
  };

  const handleModeChange = (nextMode: BillingMode) => {
    if (nextMode === activeMode) {
      return;
    }

    setActiveMode(nextMode);
    trackMarketingEvent({
      event: "pricing_mode_toggled",
      section: "pricing",
      cta: "billing_mode_toggle",
      mode: nextMode
    });

    const nextUrl = new URL(window.location.href);
    if (nextMode === "packs") {
      nextUrl.searchParams.set("pricing", "packs");
    } else {
      nextUrl.searchParams.delete("pricing");
    }
    nextUrl.hash = "pricing";
    window.history.replaceState(window.history.state, "", nextUrl);
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, currentMode: BillingMode) => {
    let nextMode: BillingMode | null = null;
    if (event.key === "Home") {
      nextMode = "subscriptions";
    } else if (event.key === "End") {
      nextMode = "packs";
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      nextMode = currentMode === "subscriptions" ? "packs" : "subscriptions";
    }

    if (!nextMode) {
      return;
    }

    event.preventDefault();
    handleModeChange(nextMode);
    event.currentTarget.parentElement
      ?.querySelector<HTMLButtonElement>(`[data-pricing-mode="${nextMode}"]`)
      ?.focus();
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.pricingToolbar}>
        <div className={styles.toggle} role="tablist" aria-label="Billing mode">
          <button
            aria-controls="pricing-subscriptions-panel"
            type="button"
            id="pricing-subscriptions-tab"
            role="tab"
            aria-selected={activeMode === "subscriptions"}
            tabIndex={activeMode === "subscriptions" ? 0 : -1}
            data-pricing-mode="subscriptions"
            className={activeMode === "subscriptions" ? styles.toggleActive : styles.toggleButton}
            onClick={() => handleModeChange("subscriptions")}
            onKeyDown={(event) => handleTabKeyDown(event, "subscriptions")}
          >
            Subscription
          </button>
          <button
            aria-controls="pricing-packs-panel"
            type="button"
            id="pricing-packs-tab"
            role="tab"
            aria-selected={activeMode === "packs"}
            tabIndex={activeMode === "packs" ? 0 : -1}
            data-pricing-mode="packs"
            className={activeMode === "packs" ? styles.toggleActive : styles.toggleButton}
            onClick={() => handleModeChange("packs")}
            onKeyDown={(event) => handleTabKeyDown(event, "packs")}
          >
            One-time packs
          </button>
        </div>

        <div className={styles.pricingMeta}>
          <span className={styles.taxDisclosure} title="Prices exclude tax">
            Excl. tax
          </span>
          <PricingCurrencySelect
            className={styles.currencyControl}
            currency={currency}
            onChange={selectCurrency}
          />
        </div>
      </div>

      <motion.div className={styles.modeViewport} layout transition={stageTransition}>
        <AnimatePresence mode="sync" initial={false}>
          <motion.div
            aria-labelledby={`pricing-${activeMode}-tab`}
            id={`pricing-${activeMode}-panel`}
            key={activeMode}
            className={styles.modeStage}
            data-mode={activeMode}
            role="tabpanel"
            initial={shouldReduceMotion ? false : { opacity: 0, y: 7 }}
            animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -5 }}
            transition={stageTransition}
          >
            <div className={styles.copyBlock}>
              <p className={styles.sectionLabel}>{copy.section_label}</p>
              <h3>{copy.headline}</h3>
              <p>{copy.subhead}</p>
            </div>

            <div className={styles.cardGrid} data-mode={activeMode}>
              {plans.map((plan) => {
                const isFeatured = Boolean(plan.highlight);
                const cardHref =
                  activeMode === "subscriptions" && plan.name.toLowerCase() === "free"
                    ? "/signup"
                    : buildPaidCheckoutHref(plan.planCode);
                const cardCtaLabel =
                  activeMode === "subscriptions" && plan.name.toLowerCase() === "free"
                    ? "Open free access"
                    : `Select ${plan.name}`;

                return (
                  <article
                    key={plan.planCode}
                    className={isFeatured ? styles.planCardFeatured : styles.planCard}
                  >
                    <header className={styles.planHeader}>
                      <div className={styles.planMeta}>
                        <p className={styles.planTag}>{plan.tag}</p>
                        <h4 className={styles.planName}>{plan.name}</h4>
                      </div>
                      {isFeatured ? <span className={styles.popularBadge}>Recommended</span> : null}
                    </header>

                    <div className={styles.planLedger}>
                      <p className={styles.planPrice}>{formatPricingPrice(plan.prices, currency)}</p>
                      <p className={styles.planHours}>{plan.hours}</p>
                    </div>

                    <ul className={styles.featureList}>
                      {plan.features.map((feature) => (
                        <li key={feature}>{feature}</li>
                      ))}
                    </ul>

                    <Link
                      href={cardHref}
                      className={isFeatured ? styles.cardCtaPrimary : styles.cardCtaGhost}
                      onClick={() => {
                        trackPricingCtaClick("card", plan.planCode);
                      }}
                    >
                      {cardCtaLabel}
                    </Link>
                  </article>
                );
              })}
            </div>

            <div className={styles.notesPanel}>
              <p className={styles.notesLabel}>{copy.notes_label}</p>
              <p className={styles.footnote}>{copy.footnote}</p>
              {copy.footnoteMuted ? <p className={styles.footnoteMuted}>{copy.footnoteMuted}</p> : null}
              {copy.benefits?.length ? (
                <ul className={styles.benefitList}>
                  {copy.benefits.map((benefit) => (
                    <li key={benefit}>{benefit}</li>
                  ))}
                </ul>
              ) : null}
            </div>

            <div className={styles.secondaryActions}>
              <Link
                href={activeMode === "subscriptions" ? buildPaidCheckoutHref(highlightedPlan.planCode) : "/signup"}
                className={styles.secondaryLink}
                onClick={() => {
                  trackPricingCtaClick("secondary", highlightedPlan.planCode);
                }}
              >
                {copy.secondary_cta}
              </Link>
            </div>
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
