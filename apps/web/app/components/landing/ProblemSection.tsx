import type { LandingContent } from "@/content/landing";

import styles from "../../page.module.css";

type ProblemSectionProps = {
  content: LandingContent["problem"];
};

export default function ProblemSection({ content }: ProblemSectionProps) {
  return (
    <section className={styles.section} aria-labelledby="problem-heading">
      <div className={styles.container}>
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>{content.eyebrow}</p>
          <h2 id="problem-heading" className={styles.sectionTitle}>
            {content.title}
          </h2>
          <p className={styles.sectionSubtitle}>{content.subtitle}</p>
        </div>

        <div className={styles.problemGrid}>
          {content.points.map((point) => (
            <article key={point.title} className={styles.problemCard}>
              <h3>{point.title}</h3>
              <p>{point.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
