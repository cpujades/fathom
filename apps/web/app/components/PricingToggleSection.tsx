"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import { packPlans, pricingCopy, subscriptionPlans } from "../content/pricing";
import { trackMarketingEvent } from "../lib/marketingEvents";
import styles from "./pricing-toggle-section.module.css";

type BillingMode = "subscriptions" | "packs";

type PricingToggleSectionProps = {
  mode: BillingMode;
};

const slugify = (value: string): string => {
  return value.trim().toLowerCase().replace(/\s+/g, "-");
};

const buildPaidCheckoutHref = (planName: string): string => {
  const params = new URLSearchParams({
    next: "/app/billing",
    intent: "paid",
    plan: slugify(planName)
  });

  return `/signup?${params.toString()}`;
};

export default function PricingToggleSection({ mode }: PricingToggleSectionProps) {
  const router = useRouter();
  const shouldReduceMotion = useReducedMotion();
  const [isPending, startTransition] = useTransition();
  const [activeMode, setActiveMode] = useState<BillingMode>(mode);

  useEffect(() => {
    setActiveMode(mode);
  }, [mode]);

  const plans = activeMode === "subscriptions" ? subscriptionPlans : packPlans;
  const highlightedPlan = plans.find((plan) => plan.highlight) ?? plans[0];
  const copy = pricingCopy[activeMode];
  const stageTransition = shouldReduceMotion
    ? { duration: 0 }
    : { duration: 0.22, ease: [0.22, 1, 0.36, 1] as const };
  const cardTransition = shouldReduceMotion
    ? { duration: 0 }
    : { duration: 0.18, ease: [0.22, 1, 0.36, 1] as const };

  const trackPricingCtaClick = (ctaName: "card" | "secondary", planName?: string) => {
    trackMarketingEvent({
      event: "pricing_plan_cta_clicked",
      section: "pricing",
      cta: ctaName,
      mode: activeMode,
      plan: slugify(planName ?? highlightedPlan?.name ?? "starter")
    });
  };

  const handleModeChange = (nextMode: BillingMode) => {
    if (nextMode === activeMode && nextMode === mode) {
      return;
    }

    setActiveMode(nextMode);
    trackMarketingEvent({
      event: "pricing_mode_toggled",
      section: "pricing",
      cta: "billing_mode_toggle",
      mode: nextMode
    });

    const href = nextMode === "packs" ? "/?pricing=packs#pricing" : "/#pricing";
    const navigate = () => {
      startTransition(() => {
        router.replace(href, { scroll: false });
      });
    };

    const transitionDocument = document as Document & {
      startViewTransition?: (update: () => void) => void;
    };

    if (transitionDocument.startViewTransition) {
      transitionDocument.startViewTransition(navigate);
      return;
    }

    navigate();
  };

  return (
    <div className={styles.wrap} data-pending={isPending ? "true" : "false"}>
      <div className={styles.toggle} role="tablist" aria-label="Billing mode">
        <button
          type="button"
          role="tab"
          aria-selected={activeMode === "subscriptions"}
          className={activeMode === "subscriptions" ? styles.toggleActive : styles.toggleButton}
          onClick={() => handleModeChange("subscriptions")}
        >
          Subscription
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeMode === "packs"}
          className={activeMode === "packs" ? styles.toggleActive : styles.toggleButton}
          onClick={() => handleModeChange("packs")}
        >
          One-time packs
        </button>
      </div>

      <div className={styles.modeViewport}>
        <AnimatePresence mode="sync" initial={false}>
          <motion.div
            key={activeMode}
            className={styles.modeStage}
            data-mode={activeMode}
            initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.995 }}
            animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, scale: 1 }}
            exit={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, scale: 0.995 }}
            transition={stageTransition}
          >
            <motion.div
              className={styles.copyBlock}
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1 }}
              transition={stageTransition}
            >
              <p className={styles.sectionLabel}>{copy.section_label}</p>
              <h3>{copy.headline}</h3>
              <p>{copy.subhead}</p>
            </motion.div>

            <div className={styles.cardGrid} data-mode={activeMode}>
              {plans.map((plan, index) => {
                const isFeatured = Boolean(plan.highlight);
                const cardHref =
                  activeMode === "subscriptions" && plan.name.toLowerCase() === "free"
                    ? "/signup"
                    : buildPaidCheckoutHref(plan.name);
                const cardCtaLabel =
                  activeMode === "subscriptions" && plan.name.toLowerCase() === "free" ? "Open free access" : "Select access";

                return (
                  <motion.article
                    key={plan.name}
                    className={isFeatured ? styles.planCardFeatured : styles.planCard}
                    initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.988 }}
                    animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, scale: 1 }}
                    transition={{
                      ...cardTransition,
                      delay: shouldReduceMotion ? 0 : index * 0.015
                    }}
                  >
                    <header className={styles.planHeader}>
                      <div className={styles.planMeta}>
                        <p className={styles.planTag}>{plan.tag}</p>
                        <h4 className={styles.planName}>{plan.name}</h4>
                      </div>
                      {isFeatured ? <span className={styles.popularBadge}>Most popular</span> : null}
                    </header>

                    <div className={styles.planLedger}>
                      <p className={styles.planPrice}>{plan.price}</p>
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
                        trackPricingCtaClick("card", plan.name);
                      }}
                    >
                      {cardCtaLabel}
                    </Link>
                  </motion.article>
                );
              })}
            </div>

            <motion.div
              className={styles.notesPanel}
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1 }}
              transition={{
                ...stageTransition,
                delay: shouldReduceMotion ? 0 : 0.04
              }}
            >
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
            </motion.div>

            <motion.div
              className={styles.secondaryActions}
              initial={shouldReduceMotion ? false : { opacity: 0 }}
              animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1 }}
              transition={{
                ...stageTransition,
                delay: shouldReduceMotion ? 0 : 0.06
              }}
            >
              <Link
                href={activeMode === "subscriptions" ? buildPaidCheckoutHref(highlightedPlan.name) : "/signup"}
                className={styles.secondaryLink}
                onClick={() => {
                  trackPricingCtaClick("secondary", highlightedPlan.name);
                }}
              >
                {copy.secondary_cta}
              </Link>
            </motion.div>
        </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
