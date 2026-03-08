"use client";

import Link from "next/link";
import { useState } from "react";

import type { Cta, NavItem } from "@/content/landing";
import SmoothScrollLink from "@/components/SmoothScrollLink";

import styles from "../../page.module.css";

type LandingHeaderProps = {
  navItems: NavItem[];
  primaryCta: Cta;
};

export default function LandingHeader({ navItems, primaryCta }: LandingHeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const closeMenu = () => {
    setIsMenuOpen(false);
  };

  return (
    <header className={styles.header}>
      <div className={styles.container}>
        <div className={styles.navShell}>
          <Link href="/" className={styles.brand} onClick={closeMenu}>
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
            <Link href={primaryCta.href} className={`${styles.button} ${styles.buttonPrimary}`}>
              {primaryCta.label}
            </Link>
            <button
              type="button"
              className={styles.menuButton}
              aria-expanded={isMenuOpen}
              aria-controls="mobile-nav"
              aria-label={isMenuOpen ? "Close menu" : "Open menu"}
              onClick={() => setIsMenuOpen((open) => !open)}
            >
              <span className={styles.menuButtonBar} aria-hidden="true" />
              <span className={styles.menuButtonBar} aria-hidden="true" />
              <span className={styles.menuButtonBar} aria-hidden="true" />
            </button>
          </div>

          <div
            id="mobile-nav"
            className={styles.mobileMenu}
            data-open={isMenuOpen}
            aria-hidden={!isMenuOpen}
          >
            <nav className={styles.mobileMenuLinks} aria-label="Mobile">
              {navItems.map((item) => (
                <SmoothScrollLink
                  key={item.href}
                  href={item.href}
                  className={styles.mobileMenuLink}
                  onClick={closeMenu}
                >
                  {item.label}
                </SmoothScrollLink>
              ))}
            </nav>
            <div className={styles.mobileMenuActions}>
              <Link href="/signin" className={`${styles.button} ${styles.buttonGhost}`} onClick={closeMenu}>
                Sign in
              </Link>
              <Link
                href={primaryCta.href}
                className={`${styles.button} ${styles.buttonPrimary}`}
                onClick={closeMenu}
              >
                {primaryCta.label}
              </Link>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
