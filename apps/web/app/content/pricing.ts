type Plan = {
  tag: string;
  name: string;
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
    section_label: "Reserve access",
    headline: "Prefer reserve credits instead?",
    subhead:
      "Use packs when listening comes in bursts. Buy time when needed, keep it for six months, and extend the window when you top up.",
    secondary_cta: "Start with a free briefing",
    notes_label: "Reserve notes",
    footnote:
      "Credits remain valid for 6 months. Top up before expiry and the remaining time rolls into a fresh 6-month window.",
    footnoteMuted:
      "Auto-refill (coming soon): buy another pack when you drop under 1 hour and unlock +10% bonus credits."
  },
  subscriptions: {
    section_label: "Standing access",
    headline: "Prefer a standing monthly brief?",
    subhead:
      "Best for steady listeners who want ready access, rollover protection, and lower effective cost as the habit compounds.",
    secondary_cta: "Go straight to paid access",
    notes_label: "Standing notes",
    benefits: [
      "Rollover - keep unused listening time in play.",
      "Readiness - always have briefing capacity on hand.",
      "Lower cost - better economics than packs at recurring usage."
    ],
    footnote:
      "Unused credits roll over for one month, up to 2x your monthly limit."
  }
};

export type { Plan, PricingCopy };
export { packPlans, subscriptionPlans, pricingCopy };
