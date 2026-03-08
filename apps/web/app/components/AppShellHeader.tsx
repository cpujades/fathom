"use client";

import Link from "next/link";

import { formatDuration } from "../lib/format";
import styles from "./app-shell-header.module.css";

type AppSection = "home" | "billing" | "history" | "profile";

type NavItem = {
  id: AppSection;
  href: string;
  label: string;
};

const NAV_ITEMS: NavItem[] = [
  { id: "home", href: "/app", label: "Home" },
  { id: "billing", href: "/app/billing", label: "Billing" },
  { id: "history", href: "/app/history", label: "History" },
  { id: "profile", href: "/app/profile", label: "Profile" }
];

type AppShellHeaderProps = {
  active: AppSection;
  remainingSeconds: number | null;
  accountLabel: string | null;
  onSignOut: () => void;
};

export function AppShellHeader({ active, remainingSeconds, accountLabel, onSignOut }: AppShellHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link className={styles.brand} href="/app" aria-label="Go to workspace home">
          <span className={styles.brandMark} aria-hidden="true" />
          Talven
        </Link>

        <nav className={styles.nav} aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.id}
              className={`${styles.navLink} ${active === item.id ? styles.navLinkActive : ""}`}
              href={item.href}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className={styles.accountCluster}>
          <div className={styles.creditsPill}>
            Remaining {remainingSeconds !== null ? formatDuration(remainingSeconds) : "-"}
          </div>
          <div className={styles.accountMenu}>
            <span className={styles.accountLabel}>{accountLabel ?? "Account"}</span>
            <button className={styles.signOutButton} type="button" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
