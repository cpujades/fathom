import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type HowItWorksSectionProps = {
  content: LandingContent["howItWorks"];
};

export default function HowItWorksSection({ content }: HowItWorksSectionProps) {
  return (
    <section id="how-it-works" className={styles.sectionAlt} aria-labelledby="how-it-works-heading">
      <div className={styles.container}>
        <div className={styles.editorialShell}>
          <div className={styles.sectionIntro}>
            <p className={styles.eyebrow}>{content.eyebrow}</p>
            <h2 id="how-it-works-heading" className={styles.sectionTitle}>
              {content.title}
            </h2>
          </div>

          <div className={styles.dossierNote}>
            <p className={styles.dossierNoteLabel}>Reading method</p>
            <p className={styles.dossierNoteText}>
              Talven is designed to cut straight from raw conversation to a format you can scan, verify, and reuse.
            </p>
          </div>
        </div>

        <ol className={styles.methodTimeline}>
          {content.steps.map((step, index) => (
            <li key={step.title} className={styles.methodStep}>
              <div className={styles.methodMarker}>
                <span>{index + 1}</span>
              </div>
              <div className={styles.methodStepBody}>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
