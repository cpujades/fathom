type NavItem = {
  label: string;
  href: string;
};

type Cta = {
  label: string;
  href: string;
};

type HeroContent = {
  eyebrow: string;
  title: string;
  subtitle: string;
  primaryCta: Cta;
  secondaryCta: Cta;
  expectations: string[];
};

type ProblemPoint = {
  title: string;
  text: string;
};

type HowItWorksStep = {
  title: string;
  text: string;
};

type ProofRow = {
  timestamp: string;
  claim: string;
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
    { label: "How it works", href: "#how-it-works" },
    { label: "Sample", href: "#proof" },
    { label: "Pricing", href: "#pricing" },
    { label: "FAQ", href: "#faq" }
  ],
  hero: {
    eyebrow: "Built for podcast listeners",
    title: "Save hours without missing signal.",
    subtitle:
      "Paste a YouTube podcast URL and get a concise, timestamped brief with key insights, takeaways, and exports in minutes.",
    primaryCta: {
      label: "Start free",
      href: "/signup"
    },
    secondaryCta: {
      label: "See sample summary",
      href: "#proof"
    },
    expectations: ["YouTube URL in", "Structured summary out", "Markdown + PDF export"]
  },
  problem: {
    eyebrow: "Why Fathom",
    title: "Your podcast backlog grows faster than your listening time.",
    subtitle: "Fathom helps you keep the useful parts and skip the noise.",
    points: [
      {
        title: "Too much content, not enough time",
        text: "Long episodes are valuable, but full playback does not fit every day."
      },
      {
        title: "Signal is hard to recover later",
        text: "Great moments get buried when you only rely on memory or scattered notes."
      },
      {
        title: "Decisions need clarity, not full transcripts",
        text: "You need the important points, sources, and next actions in one clear brief."
      }
    ]
  },
  howItWorks: {
    eyebrow: "How it works",
    title: "Three steps from episode to usable brief.",
    steps: [
      {
        title: "1. Paste a YouTube URL",
        text: "Add any supported episode to your queue in seconds."
      },
      {
        title: "2. Fathom processes the episode",
        text: "The system transcribes, summarizes, and structures the output automatically."
      },
      {
        title: "3. Review and export",
        text: "Get timestamps, key ideas, and takeaways you can share as Markdown or PDF."
      }
    ]
  },
  proof: {
    eyebrow: "Output proof",
    title: "A summary format designed for fast trust.",
    subtitle: "This section uses placeholder sample content and is ready for a real episode swap.",
    sampleLabel: "Sample summary format",
    sampleTitle: "58-minute episode -> 4-minute read",
    sampleNote: "Placeholder sample: replace with an approved real summary excerpt before launch.",
    before:
      "A full episode with multiple tangents, stories, and references across product, strategy, and execution.",
    after: [
      "Main claims prioritized by importance",
      "Timestamp anchors for each important point",
      "Actionable takeaway bullets for follow-through"
    ],
    rows: [
      {
        timestamp: "08:42",
        claim: "Guest explains the single metric they track weekly to catch GTM problems early."
      },
      {
        timestamp: "21:17",
        claim: "Host outlines why founder-led sales should transition once messaging repeatability appears."
      },
      {
        timestamp: "46:03",
        claim: "Final section lists two practical experiments teams can run in the next sprint."
      }
    ]
  },
  quality: {
    eyebrow: "Quality expectations",
    title: "Transparent about what you get.",
    subtitle: "Fathom is built for practical clarity, with concise AI transparency.",
    points: [
      {
        title: "Structured by default",
        text: "Every summary follows the same readable format so you can scan quickly."
      },
      {
        title: "Timestamp traceability",
        text: "Important statements point back to source moments for fast verification."
      },
      {
        title: "Realistic AI expectations",
        text: "Fathom prioritizes high-signal output, but you should still review critical decisions against source audio."
      }
    ],
    expectation:
      "Best fit: listeners who want fast, trustworthy synthesis for planning, sharing, and follow-up."
  },
  pricingIntro: {
    eyebrow: "Pricing",
    title: "Start free, upgrade when your listening volume grows.",
    subtitle: "Subscriptions are default. One-time packs are available for occasional spikes."
  },
  faq: {
    eyebrow: "FAQ",
    title: "Answers before you commit.",
    items: [
      {
        question: "What sources are supported right now?",
        answer: "Fathom currently supports YouTube podcast URLs."
      },
      {
        question: "How long does a summary take?",
        answer:
          "Most jobs finish in minutes depending on episode length and queue load. You can track status in your dashboard."
      },
      {
        question: "Can I export summaries to my own tools?",
        answer: "Yes. Export to Markdown or PDF for your docs and workflows."
      },
      {
        question: "Can I cancel a paid subscription anytime?",
        answer: "Yes. Cancellation is effective at period end and you keep access during the active window."
      }
    ]
  },
  finalCta: {
    title: "Keep your favorite podcasts. Summarize the rest.",
    text: "Create your free account now and decide later whether to stay free, subscribe, or use one-time packs.",
    primaryCta: {
      label: "Start free",
      href: "/signup"
    },
    secondaryCta: {
      label: "Jump to pricing",
      href: "#pricing"
    }
  },
  footer: {
    copyright: "Copyright 2026 Fathom",
    links: [
      { label: "Pricing", href: "#pricing" },
      { label: "Sign in", href: "/signin" },
      { label: "contact@fathom.ai", href: "mailto:contact@fathom.ai" }
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
