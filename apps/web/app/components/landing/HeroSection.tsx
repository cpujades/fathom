"use client";

import Link from "next/link";

import type { HeroContent } from "@/content/landing";
import { trackMarketingEvent } from "@/lib/marketingEvents";
import SmoothScrollLink from "@/components/SmoothScrollLink";

import styles from "../../page.module.css";

type HeroSectionProps = {
  content: HeroContent;
};

export default function HeroSection({ content }: HeroSectionProps) {
  return (
    <section className={styles.hero} aria-labelledby="hero-heading">
      <div className={styles.container}>
        <div className={styles.heroGrid}>
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>{content.eyebrow}</p>
            <h1 id="hero-heading" className={styles.heroTitle}>
              {content.title}
            </h1>
            <p className={styles.heroSubtitle}>{content.subtitle}</p>

            <div className={styles.heroActions}>
              <Link
                href={content.primaryCta.href}
                className={`${styles.button} ${styles.buttonPrimary}`}
                onClick={() => {
                  trackMarketingEvent({
                    event: "hero_primary_cta_clicked",
                    section: "hero",
                    cta: "start_free"
                  });
                }}
              >
                {content.primaryCta.label}
              </Link>
              <SmoothScrollLink
                href={content.secondaryCta.href}
                className={`${styles.button} ${styles.buttonGhost}`}
                onClick={() => {
                  trackMarketingEvent({
                    event: "hero_secondary_cta_clicked",
                    section: "hero",
                    cta: "see_sample_summary"
                  });
                }}
              >
                {content.secondaryCta.label}
              </SmoothScrollLink>
            </div>

            <ul className={styles.expectationList}>
              {content.expectations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <aside className={styles.heroAside} aria-label="What to expect">
            <p className={styles.cardEyebrow}>What to expect</p>
            <h2 className={styles.cardTitle}>Concise briefs with traceable context</h2>
            <p className={styles.cardText}>
              Fathom is optimized for listeners who want decisions and clarity, not verbatim transcripts.
            </p>
            <div className={styles.cardStatGrid}>
              <div>
                <span className={styles.cardStatLabel}>Input</span>
                <p className={styles.cardStatValue}>YouTube podcast URL</p>
              </div>
              <div>
                <span className={styles.cardStatLabel}>Output</span>
                <p className={styles.cardStatValue}>Timestamped summary</p>
              </div>
              <div>
                <span className={styles.cardStatLabel}>Format</span>
                <p className={styles.cardStatValue}>Markdown + PDF</p>
              </div>
              <div>
                <span className={styles.cardStatLabel}>Goal</span>
                <p className={styles.cardStatValue}>Save hours, keep signal</p>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
