import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type ProofSectionProps = {
  content: LandingContent["proof"];
};

export default function ProofSection({ content }: ProofSectionProps) {
  return (
    <section id="proof" className={styles.section} aria-labelledby="proof-heading">
      <div className={styles.container}>
        <div className={styles.editorialShell}>
          <div className={styles.sectionIntro}>
            <p className={styles.eyebrow}>{content.eyebrow}</p>
            <h2 id="proof-heading" className={styles.sectionTitle}>
              {content.title}
            </h2>
            <p className={styles.sectionSubtitle}>{content.subtitle}</p>
          </div>

          <div className={styles.dossierNote}>
            <p className={styles.dossierNoteLabel}>Why this comes early</p>
            <p className={styles.dossierNoteText}>The briefing itself is the product. Everything else should be read as support.</p>
          </div>
        </div>

        <div className={styles.proofDossier}>
          <div className={styles.proofHeader}>
            <div>
              <p className={styles.proofLabel}>{content.sampleLabel}</p>
              <h3>{content.sampleTitle}</h3>
            </div>
            <div className={styles.proofChips}>
              <span>Traceable</span>
              <span>Condensed</span>
              <span>Actionable</span>
            </div>
          </div>

          <p className={styles.proofNote}>{content.sampleNote}</p>

          <div className={styles.proofShell}>
            <aside className={styles.proofSidebar}>
              <article className={styles.beforeAfterCard}>
                <p className={styles.beforeAfterLabel}>Source conversation</p>
                <p>{content.before}</p>
              </article>
              <article className={styles.beforeAfterCard}>
                <p className={styles.beforeAfterLabel}>What survives the cut</p>
                <ul>
                  {content.after.map((entry) => (
                    <li key={entry}>{entry}</li>
                  ))}
                </ul>
              </article>
            </aside>

            <div className={styles.proofRows}>
              {content.rows.map((row, index) => (
                <article key={row.timestamp} className={styles.proofRow}>
                  <div className={styles.proofRowMeta}>
                    <span>{row.timestamp}</span>
                    <p className={styles.proofRowIndex}>Key point {index + 1}</p>
                  </div>
                  <p>{row.claim}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
