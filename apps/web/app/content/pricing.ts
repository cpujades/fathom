type Plan = {
  tag: string;
  name: string;
  planCode: string;
  prices: PricingPrices;
  hours: string;
  features: string[];
  highlight?: boolean;
};

type PricingCurrency = "eur" | "usd" | "gbp";

type PricingPrices = Record<PricingCurrency, number>;

type PricingCopy = {
  section_label: string;
  headline: string;
  subhead: string;
  footnote: string;
  secondary_cta: string;
  notes_label: string;
  footnoteMuted?: string;
  benefits?: string[];
};

type AuthPlanSummary = {
  includedTime: string;
  paymentCadence: "monthly" | "one-time";
  planCode: string;
  prices: PricingPrices;
  productName: string;
};

const packPlans: Plan[] = [
  {
    tag: "Trial pack",
    name: "Trial",
    planCode: "trial_pack",
    prices: { eur: 600, usd: 700, gbp: 550 },
    hours: "3 hours",
    features: [
      "One-time credits, no commitment",
      "Each purchase is valid for 90 days",
      "PDF + Markdown exports"
    ]
  },
  {
    tag: "Creator pack",
    name: "Creator",
    planCode: "creator_pack",
    prices: { eur: 1800, usd: 2100, gbp: 1600 },
    hours: "10 hours",
    features: [
      "Best starter value",
      "Independent 90-day expiry",
      "PDF + Markdown exports"
    ],
    highlight: true
  },
  {
    tag: "Studio pack",
    name: "Studio",
    planCode: "studio_pack",
    prices: { eur: 6000, usd: 6900, gbp: 5200 },
    hours: "40 hours",
    features: [
      "Largest pack for heavy users",
      "Independent 90-day expiry",
      "No monthly fees"
    ]
  }
];

const subscriptionPlans: Plan[] = [
  {
    tag: "Free",
    name: "Free",
    planCode: "free",
    prices: { eur: 0, usd: 0, gbp: 0 },
    hours: "1 hour / month",
    features: ["Summaries + PDF export", "Email + magic link", "Monthly reset"]
  },
  {
    tag: "Starter",
    name: "Starter",
    planCode: "starter",
    prices: { eur: 900, usd: 1000, gbp: 800 },
    hours: "6 hours / month",
    features: [
      "Unused time carries into the next month",
      "Balance stays within 2x the monthly allowance",
      "PDF + Markdown exports"
    ],
    highlight: true
  },
  {
    tag: "Pro",
    name: "Pro",
    planCode: "pro",
    prices: { eur: 1900, usd: 2200, gbp: 1700 },
    hours: "15 hours / month",
    features: [
      "Higher monthly hours",
      "One-month carryover, up to 2x the allowance",
      "PDF + Markdown exports"
    ]
  },
  {
    tag: "Agency",
    name: "Agency",
    planCode: "agency",
    prices: { eur: 4900, usd: 5600, gbp: 4200 },
    hours: "50 hours / month",
    features: [
      "Highest monthly hours",
      "One-month carryover, up to 2x the allowance",
      "Best for heavy usage"
    ]
  }
];

const resolvePricingPrices = (planCode: string): PricingPrices | null => {
  const plan =
    subscriptionPlans.find((candidate) => candidate.planCode === planCode) ??
    packPlans.find((candidate) => candidate.planCode === planCode);
  return plan?.prices ?? null;
};

const resolveAuthPlanSummary = (intent?: string | null, planCode?: string | null): AuthPlanSummary | null => {
  if (intent !== "paid" || !planCode) {
    return null;
  }

  const normalizedPlanCode = planCode.trim().toLowerCase();
  const subscription = subscriptionPlans.find(
    (plan) => plan.planCode !== "free" && plan.planCode === normalizedPlanCode
  );
  if (subscription) {
    return {
      includedTime: subscription.hours,
      paymentCadence: "monthly",
      planCode: subscription.planCode,
      prices: subscription.prices,
      productName: subscription.name
    };
  }

  const pack = packPlans.find((plan) => plan.planCode === normalizedPlanCode);
  if (!pack) {
    return null;
  }

  return {
    includedTime: pack.hours,
    paymentCadence: "one-time",
    planCode: pack.planCode,
    prices: pack.prices,
    productName: `${pack.name} Pack`
  };
};

const pricingCopy: Record<"packs" | "subscriptions", PricingCopy> = {
  packs: {
    section_label: "One-time packs",
    headline: "Prefer to pay only when you need more time?",
    subhead:
      "Use packs when briefing needs come in bursts. Every purchase has its own balance and remains available for 90 days.",
    secondary_cta: "Start with a free briefing",
    notes_label: "Pack details",
    footnote: "Each pack expires independently 90 days after purchase."
  },
  subscriptions: {
    section_label: "Monthly plans",
    headline: "Expect to create briefings regularly?",
    subhead:
      "Best for steady users who want ready access, rollover protection, and lower effective cost as the habit compounds.",
    secondary_cta: "Go straight to paid access",
    notes_label: "Plan details",
    benefits: [
      "Carryover - keep unused time for one additional billing month.",
      "Readiness - always have briefing capacity on hand.",
      "Lower cost - better economics than packs at recurring usage."
    ],
    footnote:
      "Paid-plan time carries into the next billing month only, keeping the balance within 2x the monthly allowance."
  }
};

export type { AuthPlanSummary, Plan, PricingCopy, PricingCurrency, PricingPrices };
export { packPlans, pricingCopy, resolveAuthPlanSummary, resolvePricingPrices, subscriptionPlans };
