import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type HowItWorksSectionProps = {
  content: LandingContent["howItWorks"];
};

export default function HowItWorksSection({ content }: HowItWorksSectionProps) {
  return (
    <section id="how-it-works" className={styles.sectionAlt} aria-labelledby="how-it-works-heading">
      <div className={styles.container}>
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>{content.eyebrow}</p>
          <h2 id="how-it-works-heading" className={styles.sectionTitle}>
            {content.title}
          </h2>
        </div>

        <ol className={styles.stepGrid}>
          {content.steps.map((step) => (
            <li key={step.title} className={styles.stepCard}>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
