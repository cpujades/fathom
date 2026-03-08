type NavItem = {
  label: string;
  href: string;
};

type Cta = {
  label: string;
  href: string;
};

type ProofRow = {
  timestamp: string;
  claim: string;
};

type HeroContent = {
  eyebrow: string;
  deck: string;
  title: string;
  subtitle: string;
  primaryCta: Cta;
  secondaryCta: Cta;
  expectations: string[];
  previewRows: ProofRow[];
};

type ProblemPoint = {
  title: string;
  text: string;
};

type HowItWorksStep = {
  title: string;
  text: string;
};

type QualityPoint = {
  title: string;
  text: string;
};

type FaqItem = {
  question: string;
  answer: string;
};

type LandingContent = {
  nav: NavItem[];
  hero: HeroContent;
  problem: {
    eyebrow: string;
    title: string;
    subtitle: string;
    points: ProblemPoint[];
  };
  howItWorks: {
    eyebrow: string;
    title: string;
    steps: HowItWorksStep[];
  };
  proof: {
    eyebrow: string;
    title: string;
    subtitle: string;
    sampleLabel: string;
    sampleTitle: string;
    sampleNote: string;
    before: string;
    after: string[];
    rows: ProofRow[];
  };
  quality: {
    eyebrow: string;
    title: string;
    subtitle: string;
    points: QualityPoint[];
    expectation: string;
  };
  pricingIntro: {
    eyebrow: string;
    title: string;
    subtitle: string;
  };
  faq: {
    eyebrow: string;
    title: string;
    items: FaqItem[];
  };
  finalCta: {
    title: string;
    text: string;
    primaryCta: Cta;
    secondaryCta: Cta;
  };
  footer: {
    copyright: string;
    links: Cta[];
  };
};

const landingContent: LandingContent = {
  nav: [
    { label: "Method", href: "#how-it-works" },
    { label: "Sample brief", href: "#proof" },
    { label: "Pricing", href: "#pricing" },
    { label: "Questions", href: "#faq" }
  ],
  hero: {
    eyebrow: "Private podcast briefings",
    deck: "Private brief / Source-linked / Ready in minutes",
    title: "Extract the signal. Keep the edge.",
    subtitle:
      "Talven turns long podcast conversations into clear, timestamped briefings for people who prefer advantage to backlog.",
    primaryCta: {
      label: "Get your first briefing",
      href: "/signup"
    },
    secondaryCta: {
      label: "Read the sample brief",
      href: "#proof"
    },
    expectations: ["YouTube link in", "Briefing out", "Markdown + PDF ready"],
    previewRows: [
      {
        timestamp: "08:42",
        claim: "Guest identifies the weekly GTM metric they use to spot weakness before it compounds."
      },
      {
        timestamp: "21:17",
        claim: "Host explains why founder-led sales should end once messaging becomes repeatable."
      },
      {
        timestamp: "46:03",
        claim: "Episode closes with two experiments the listener can run in the next week."
      }
    ]
  },
  problem: {
    eyebrow: "Why it matters",
    title: "Most podcast value disappears into the hour you never revisit.",
    subtitle: "Talven keeps the ideas worth carrying forward, without asking you to relisten.",
    points: [
      {
        title: "Long conversations hide a few usable ideas",
        text: "Most episodes contain a small number of points that actually change how you think or act."
      },
      {
        title: "Memory is not a retrieval system",
        text: "Useful moments vanish quickly when they live only in your head or in half-finished notes."
      },
      {
        title: "Insight loses value when it arrives late",
        text: "You need the point, the source, and the takeaway before the idea goes cold."
      }
    ]
  },
  howItWorks: {
    eyebrow: "Briefing flow",
    title: "From open conversation to usable briefing.",
    steps: [
      {
        title: "Submit an episode",
        text: "Drop in a YouTube podcast link and send it straight into the queue."
      },
      {
        title: "Talven extracts the signal",
        text: "The system transcribes, condenses, and structures the conversation into a readable briefing."
      },
      {
        title: "Read, verify, and export",
        text: "Review the key points, trace them to source moments, and export the briefing when needed."
      }
    ]
  },
  proof: {
    eyebrow: "Evidence",
    title: "Built to read like a briefing, not a transcript.",
    subtitle: "Talven condenses the ideas worth keeping and anchors them to source moments you can verify.",
    sampleLabel: "Sample brief",
    sampleTitle: "58-minute episode -> 4-minute briefing",
    sampleNote: "Each Talven briefing keeps the same reading logic: key claims first, source moments attached, next moves made clear.",
    before: "A long conversation spanning strategy, execution, and personal operating principles.",
    after: [
      "Key claims ranked by importance",
      "Source moments attached to material points",
      "Clear takeaways you can reuse or act on"
    ],
    rows: [
      {
        timestamp: "08:42",
        claim: "Guest explains the single metric they track weekly to catch GTM weakness before it compounds."
      },
      {
        timestamp: "21:17",
        claim: "Host outlines why founder-led sales should end once messaging becomes repeatable."
      },
      {
        timestamp: "46:03",
        claim: "Final section ends with two practical experiments a listener could run in the next week."
      }
    ]
  },
  quality: {
    eyebrow: "Method",
    title: "Structured for signal, grounded in source.",
    subtitle: "Talven is built for readable synthesis with enough traceability to verify what matters.",
    points: [
      {
        title: "Briefing-first format",
        text: "Every output follows the same disciplined structure so it reads fast and stays usable."
      },
      {
        title: "Timestamp traceability",
        text: "Material claims point back to source moments so you can verify the original context quickly."
      },
      {
        title: "Disciplined AI use",
        text: "Talven favors concise synthesis over bloated recaps, but critical decisions should still be checked against source audio."
      }
    ],
    expectation: "Best fit: listeners who want sharper thinking without turning every episode into homework."
  },
  pricingIntro: {
    eyebrow: "Pricing",
    title: "Choose a standing brief or a measured reserve.",
    subtitle: "Subscriptions fit steady listening. Credit packs cover occasional bursts without a monthly commitment."
  },
  faq: {
    eyebrow: "Questions",
    title: "What people ask before they begin.",
    items: [
      {
        question: "What sources are supported right now?",
        answer: "Talven currently supports YouTube podcast URLs."
      },
      {
        question: "How long does a briefing take?",
        answer:
          "Most jobs finish in minutes depending on episode length and queue load. You can track each briefing from your workspace."
      },
      {
        question: "Can I export briefings to my own tools?",
        answer: "Yes. Export each briefing to Markdown or PDF for your notes, docs, or workflows."
      },
      {
        question: "Can I cancel a paid subscription anytime?",
        answer: "Yes. Cancellation is effective at period end and you keep access during the active window."
      }
    ]
  },
  finalCta: {
    title: "Build a private edge from what you listen to.",
    text: "Start with one episode. Read the briefing. Decide if Talven belongs in your weekly stack.",
    primaryCta: {
      label: "Get your first briefing",
      href: "/signup"
    },
    secondaryCta: {
      label: "See pricing",
      href: "#pricing"
    }
  },
  footer: {
    copyright: "Copyright 2026 Talven",
    links: [
      { label: "Pricing", href: "#pricing" },
      { label: "Sign in", href: "/signin" },
      { label: "Contact", href: "mailto:contact@talven.ai" }
    ]
  }
};

export type {
  Cta,
  FaqItem,
  HeroContent,
  HowItWorksStep,
  LandingContent,
  NavItem,
  ProblemPoint,
  ProofRow,
  QualityPoint
};
export { landingContent };
