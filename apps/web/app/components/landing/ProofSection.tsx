import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type ProofSectionProps = {
  content: LandingContent["proof"];
};

export default function ProofSection({ content }: ProofSectionProps) {
  return (
    <section id="proof" className={styles.section} aria-labelledby="proof-heading">
      <div className={styles.container}>
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>{content.eyebrow}</p>
          <h2 id="proof-heading" className={styles.sectionTitle}>
            {content.title}
          </h2>
          <p className={styles.sectionSubtitle}>{content.subtitle}</p>
        </div>

        <div className={styles.proofShell}>
          <div className={styles.proofMeta}>
            <p className={styles.proofLabel}>{content.sampleLabel}</p>
            <h3>{content.sampleTitle}</h3>
            <p className={styles.proofNote}>{content.sampleNote}</p>

            <div className={styles.beforeAfterGrid}>
              <article className={styles.beforeAfterCard}>
                <p className={styles.beforeAfterLabel}>Before</p>
                <p>{content.before}</p>
              </article>
              <article className={styles.beforeAfterCard}>
                <p className={styles.beforeAfterLabel}>After</p>
                <ul>
                  {content.after.map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </article>
            </div>
          </div>

          <div className={styles.proofRows}>
            {content.rows.map((row) => (
              <article key={row.timestamp} className={styles.proofRow}>
                <span>{row.timestamp}</span>
                <p>{row.claim}</p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
