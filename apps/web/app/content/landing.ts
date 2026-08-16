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
  note: string;
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
    { label: "Explore", href: "/explore" },
    { label: "Method", href: "#how-it-works" },
    { label: "Sample brief", href: "#proof" },
    { label: "Pricing", href: "#pricing" },
    { label: "Questions", href: "#faq" }
  ],
  hero: {
    eyebrow: "Source-linked YouTube briefings",
    deck: "Source-linked / Track progress / Export anytime",
    title: "Extract the signal. Keep the edge.",
    subtitle:
      "Talven turns long-form YouTube videos into clear, source-linked briefings for people who prefer advantage to backlog.",
    primaryCta: {
      label: "Get your first briefing",
      href: "/signup"
    },
    secondaryCta: {
      label: "Read the sample brief",
      href: "#proof"
    },
    expectations: ["YouTube link in", "Briefing out", "Markdown + PDF ready"],
    note: "Includes key claims, source moments, and export-ready output without the transcript sprawl."
  },
  problem: {
    eyebrow: "Why it matters",
    title: "Most long-form video value disappears into the hour you never revisit.",
    subtitle: "Talven keeps the ideas worth carrying forward, without asking you to rewatch.",
    points: [
      {
        title: "Long conversations hide a few usable ideas",
        text: "Most long videos contain a small number of points that actually change how you think or act."
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
        title: "Submit a video",
        text: "Drop in a public YouTube link and send it straight into the queue."
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
    eyebrow: "Source traceability",
    title: "Built to read like a briefing, not a transcript.",
    subtitle: "Talven condenses the ideas worth keeping and anchors them to source moments you can verify.",
    sampleLabel: "Sample brief",
    sampleTitle: "58-minute video -> 4-minute briefing",
    sampleNote: "Illustrative example, not a customer result: key claims first, source moments attached, next moves made clear.",
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
        claim: "Final section ends with two practical experiments a viewer could run in the next week."
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
        text: "Briefings follow the same disciplined structure so they read fast and stay usable."
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
    expectation: "Best fit: people who want sharper thinking without turning every long video into homework."
  },
  pricingIntro: {
    eyebrow: "Pricing",
    title: "Choose monthly access or a one-time pack.",
    subtitle: "Monthly plans fit steady use. Video-time packs cover occasional bursts without a recurring charge."
  },
  faq: {
    eyebrow: "Questions",
    title: "What people ask before they begin.",
    items: [
      {
        question: "What sources are supported right now?",
        answer: "Talven currently supports public YouTube URLs."
      },
      {
        question: "How long does a briefing take?",
        answer:
          "Processing time depends on video length, queue load, and provider availability. You can track each briefing from your workspace and return when it is ready."
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
    title: "Keep the useful parts of what you watch.",
    text: "Start with one video. Read the briefing. Decide if Talven belongs in your weekly stack.",
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
      { label: "Explore", href: "/explore" },
      { label: "Pricing", href: "#pricing" },
      { label: "Sign in", href: "/signin" },
      { label: "Privacy", href: "/privacy" },
      { label: "Terms", href: "/terms" },
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
