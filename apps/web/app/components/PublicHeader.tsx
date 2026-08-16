import Link from "next/link";

import styles from "./public-header.module.css";

export function PublicHeader() {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link className={styles.brand} href="/" aria-label="Talven home">
          <span className={styles.brandMark} aria-hidden="true" />
          <span>Talven</span>
        </Link>
        <nav className={styles.navigation} aria-label="Public navigation">
          <Link href="/explore">Explore</Link>
          <Link href="/signin">Sign in</Link>
          <Link className={styles.primaryAction} href="/signup">Create a briefing</Link>
        </nav>
      </div>
    </header>
  );
}
