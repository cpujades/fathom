import styles from "../resilience.module.css";

export default function AppLoading() {
  return (
    <main id="main-content" className={styles.page}>
      <section className={styles.loadingCard} aria-busy="true" aria-labelledby="workspace-loading-title">
        <p className={styles.kicker}>Talven workspace</p>
        <h1 className={styles.title} id="workspace-loading-title">
          Opening your workspace
        </h1>
        <p className={styles.copy}>Your saved briefings and account details are loading.</p>
        <div className={styles.loadingLine} aria-hidden="true" />
        <div className={styles.loadingLineShort} aria-hidden="true" />
        <span className={styles.visuallyHidden} role="status">
          Loading workspace
        </span>
      </section>
    </main>
  );
}
