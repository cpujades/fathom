import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type QualitySectionProps = {
  content: LandingContent["quality"];
};

export default function QualitySection({ content }: QualitySectionProps) {
  return (
    <section className={styles.sectionAlt} aria-labelledby="quality-heading">
      <div className={styles.container}>
        <div className={styles.editorialShell}>
          <div className={styles.sectionIntro}>
            <p className={styles.eyebrow}>{content.eyebrow}</p>
            <h2 id="quality-heading" className={styles.sectionTitle}>
              {content.title}
            </h2>
            <p className={styles.sectionSubtitle}>{content.subtitle}</p>
          </div>

          <div className={styles.dossierNote}>
            <p className={styles.dossierNoteLabel}>Trust condition</p>
            <p className={styles.dossierNoteText}>
              The briefing should feel lighter than the source material, but never detached from it.
            </p>
          </div>
        </div>

        <div className={styles.qualityGrid}>
          {content.points.map((point) => (
            <article key={point.title} className={styles.qualityCard}>
              <h3>{point.title}</h3>
              <p>{point.text}</p>
            </article>
          ))}
        </div>

        <p className={styles.qualityExpectation}>{content.expectation}</p>
      </div>
    </section>
  );
}
