import Link from "next/link";

import styles from "./resilience.module.css";

export default function NotFound() {
  return (
    <main id="main-content" className={styles.page}>
      <section className={styles.card} aria-labelledby="not-found-title">
        <p className={styles.kicker}>Page not found</p>
        <h1 className={styles.title} id="not-found-title">
          This page is not in Talven
        </h1>
        <p className={styles.copy}>The link may be out of date. Return home or open your briefing workspace.</p>
        <div className={styles.actions}>
          <Link className={styles.primaryAction} href="/">
            Return home
          </Link>
          <Link className={styles.secondaryAction} href="/app">
            Open workspace
          </Link>
        </div>
      </section>
    </main>
  );
}
