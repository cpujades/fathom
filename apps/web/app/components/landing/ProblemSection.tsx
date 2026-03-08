import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type ProblemSectionProps = {
  content: LandingContent["problem"];
};

export default function ProblemSection({ content }: ProblemSectionProps) {
  return (
    <section className={styles.section} aria-labelledby="problem-heading">
      <div className={styles.container}>
        <div className={styles.editorialShell}>
          <div className={styles.sectionIntro}>
            <p className={styles.eyebrow}>{content.eyebrow}</p>
            <h2 id="problem-heading" className={styles.sectionTitle}>
              {content.title}
            </h2>
            <p className={styles.sectionSubtitle}>{content.subtitle}</p>
          </div>

          <div className={styles.dossierNote}>
            <p className={styles.dossierNoteLabel}>Reader&apos;s problem</p>
            <p className={styles.dossierNoteText}>
              The issue is not access to information. It is holding on to the few moments that actually change how you think.
            </p>
          </div>
        </div>

        <div className={styles.problemStack}>
          {content.points.map((point, index) => (
            <article key={point.title} className={styles.problemEntry}>
              <p className={styles.problemIndex}>0{index + 1}</p>
              <div className={styles.problemEntryBody}>
                <h3>{point.title}</h3>
                <p>{point.text}</p>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
