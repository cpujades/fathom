type Plan = {
  tag: string;
  name: string;
  price: string;
  hours: string;
  features: string[];
  highlight?: boolean;
};

type PricingCopy = {
  headline: string;
  subhead: string;
  footnote: string;
  footnoteMuted?: string;
  benefits?: string[];
};

const packPlans: Plan[] = [
  {
    tag: "Trial pack",
    name: "Trial",
    price: "$5",
    hours: "3 hours",
    features: [
      "One-time credits, no commitment",
      "Credits valid for 6 months",
      "PDF + Markdown exports"
    ]
  },
  {
    tag: "Creator pack",
    name: "Creator",
    price: "$15",
    hours: "10 hours",
    features: [
      "Best starter value",
      "Top up to extend expiry",
      "PDF + Markdown exports"
    ],
    highlight: true
  },
  {
    tag: "Studio pack",
    name: "Studio",
    price: "$50",
    hours: "40 hours",
    features: [
      "Largest pack for heavy listeners",
      "Top up anytime to extend",
      "No monthly fees"
    ]
  }
];

const subscriptionPlans: Plan[] = [
  {
    tag: "Free",
    name: "Free",
    price: "$0",
    hours: "1 hour / month",
    features: ["Summaries + PDF export", "Email + magic link", "Monthly reset"]
  },
  {
    tag: "Starter",
    name: "Starter",
    price: "$9",
    hours: "6 hours / month",
    features: [
      "Unused hours roll over",
      "Rollover up to 2x monthly limit",
      "PDF + Markdown exports"
    ],
    highlight: true
  },
  {
    tag: "Pro",
    name: "Pro",
    price: "$19",
    hours: "15 hours / month",
    features: ["Higher monthly hours", "Rollover up to 2x monthly limit", "PDF + Markdown exports"]
  },
  {
    tag: "Agency",
    name: "Agency",
    price: "$49",
    hours: "50 hours / month",
    features: [
      "Highest monthly hours",
      "Rollover up to 2x monthly limit",
      "Best for heavy usage"
    ]
  }
];

const pricingCopy: Record<"packs" | "subscriptions", PricingCopy> = {
  packs: {
    headline: "Not ready to subscribe? Looking for one-time credits?",
    subhead:
      "Buy a pack and skip the subscription. No monthly fees. Pay only for the hours you listen to. Credits are valid for 6 months and extend with top-ups.",
    footnote:
      "Credits last 6 months. If you top up before expiry, remaining hours roll into the new 6-month window.",
    footnoteMuted:
      "Auto-refill (coming soon): buy another pack when you drop under 1 hour and unlock +10% bonus credits."
  },
  subscriptions: {
    headline: "Prefer a predictable monthly plan?",
    subhead:
      "Best for steady listeners. Monthly hours with rollover protection, so unused time carries forward.",
    benefits: [
      "Rollover — Don't lose your hours.",
      "Peace of mind — Always ready when you need it.",
      "Lower price — Save about 15% vs packs on most tiers."
    ],
    footnote:
      "Unused credits roll over for one month, up to 2x your monthly limit."
  }
};

export type { Plan, PricingCopy };
export { packPlans, subscriptionPlans, pricingCopy };
