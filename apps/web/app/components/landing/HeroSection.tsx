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
            <p className={styles.heroDeck}>{content.deck}</p>
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
                    cta: "see_sample_briefing"
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

          <aside className={styles.heroAside} aria-label="Briefing preview">
            <div className={styles.dossierMasthead}>
              <p className={styles.cardEyebrow}>Talven brief</p>
              <span className={styles.dossierSeal}>Private intelligence</span>
            </div>
            <h2 className={styles.cardTitle}>A briefing layer for the conversations worth keeping.</h2>
            <p className={styles.cardText}>
              Every Talven brief compresses the hours, preserves the source moments, and leaves you with the few ideas worth carrying into action.
            </p>

            <div className={styles.heroCoverSheet}>
              <div className={styles.coverRow}>
                <span className={styles.coverLabel}>Source</span>
                <p className={styles.coverValue}>Long-form podcast conversation</p>
              </div>
              <div className={styles.coverRow}>
                <span className={styles.coverLabel}>Form</span>
                <p className={styles.coverValue}>Source-linked briefing</p>
              </div>
              <div className={styles.coverRow}>
                <span className={styles.coverLabel}>Read time</span>
                <p className={styles.coverValue}>Condensed to the essential minutes</p>
              </div>
            </div>

            <p className={styles.heroAsideNote}>{content.note}</p>
          </aside>
        </div>
      </div>
    </section>
  );
}
