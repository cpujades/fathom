"use client";

import Link from "next/link";

import type { Cta, NavItem } from "@/content/landing";
import SmoothScrollLink from "@/components/SmoothScrollLink";

import styles from "../../page.module.css";

type LandingHeaderProps = {
  navItems: NavItem[];
  primaryCta: Cta;
};

export default function LandingHeader({ navItems, primaryCta }: LandingHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <div className={styles.navShell}>
          <Link href="/" className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true" />
            <span className={styles.brandText}>
              <span className={styles.brandMeta}>Private intelligence</span>
              <span className={styles.brandWord}>Talven</span>
            </span>
          </Link>

          <div className={styles.navFrame}>
            <nav className={styles.nav} aria-label="Main">
              {navItems.map((item) => (
                <SmoothScrollLink key={item.href} href={item.href}>
                  {item.label}
                </SmoothScrollLink>
              ))}
            </nav>
          </div>

          <div className={styles.navActions}>
            <Link href="/signin" className={`${styles.button} ${styles.buttonGhost}`}>
              Sign in
            </Link>
            <Link href={primaryCta.href} className={`${styles.button} ${styles.buttonPrimary}`}>
              {primaryCta.label}
            </Link>
          </div>

          <div className={styles.mobileControls}>
            <Link href="/signin" className={`${styles.button} ${styles.buttonGhost}`}>
              Sign in
            </Link>
            <Link href={primaryCta.href} className={`${styles.button} ${styles.buttonPrimary}`}>
              Start briefing
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
