type Plan = {
  tag: string;
  name: string;
  planCode: string;
  price: string;
  hours: string;
  features: string[];
  highlight?: boolean;
};

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
  price: string;
  productName: string;
};

const packPlans: Plan[] = [
  {
    tag: "Trial pack",
    name: "Trial",
    planCode: "trial_pack",
    price: "€6 · $7 · £5.50",
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
    price: "€18 · $21 · £16",
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
    price: "€60 · $69 · £52",
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
    price: "Free",
    hours: "1 hour / month",
    features: ["Summaries + PDF export", "Email + magic link", "Monthly reset"]
  },
  {
    tag: "Starter",
    name: "Starter",
    planCode: "starter",
    price: "€9 · $10 · £8",
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
    price: "€19 · $22 · £17",
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
    price: "€49 · $56 · £42",
    hours: "50 hours / month",
    features: [
      "Highest monthly hours",
      "One-month carryover, up to 2x the allowance",
      "Best for heavy usage"
    ]
  }
];

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
      price: subscription.price,
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
    price: pack.price,
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
    footnote:
      "Each pack expires independently 90 days after purchase. EUR is used in euro countries, GBP in the UK, and USD elsewhere. Prices exclude tax; applicable tax is added at checkout."
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
      "Paid-plan time carries into the next billing month only, keeping the balance within 2x the monthly allowance. EUR is used in euro countries, GBP in the UK, and USD elsewhere. Prices exclude tax; applicable tax is added at checkout."
  }
};

export type { AuthPlanSummary, Plan, PricingCopy };
export { packPlans, pricingCopy, resolveAuthPlanSummary, subscriptionPlans };
