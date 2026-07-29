import styles from "./resilience.module.css";

export default function RootLoading() {
  return (
    <main id="main-content" className={styles.page}>
      <section className={styles.loadingCard} aria-busy="true" aria-labelledby="route-loading-title">
        <p className={styles.kicker}>Talven</p>
        <h1 className={styles.title} id="route-loading-title">
          Opening your page
        </h1>
        <p className={styles.copy}>Your destination is loading now.</p>
        <div className={styles.loadingLine} aria-hidden="true" />
        <div className={styles.loadingLineShort} aria-hidden="true" />
        <span className={styles.visuallyHidden} role="status">
          Loading page
        </span>
      </section>
    </main>
  );
}
