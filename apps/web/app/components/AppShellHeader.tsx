"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { formatDuration } from "../lib/format";
import styles from "./app-shell-header.module.css";

type AppSection = "home" | "billing" | "briefings" | "account";

type NavItem = {
  id: AppSection;
  href: string;
  label: string;
};

const NAV_ITEMS: NavItem[] = [
  { id: "home", href: "/app", label: "Workspace" },
  { id: "briefings", href: "/app/briefings", label: "Briefings" },
  { id: "billing", href: "/app/billing", label: "Billing" }
];

type AppShellHeaderProps = {
  active?: AppSection | null;
  remainingSeconds: number | null;
  accountLabel: string | null;
  onSignOut?: () => void;
};

function getInitials(accountLabel: string | null): string {
  if (!accountLabel) {
    return "T";
  }

  const parts = accountLabel
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);

  if (parts.length === 0) {
    return "T";
  }

  return parts
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);
}

export function AppShellHeader({ active = null, remainingSeconds, accountLabel, onSignOut }: AppShellHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [menuOpen]);

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link className={styles.brand} href="/app" aria-label="Go to workspace home">
          <span className={styles.brandMark} aria-hidden="true" />
          <span className={styles.brandText}>
            <span className={styles.brandWord}>Talven</span>
          </span>
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

        {remainingSeconds !== null || accountLabel || onSignOut ? (
          <div className={styles.utilityCluster}>
            {remainingSeconds !== null ? (
              <div className={styles.balanceReadout}>
                <span className={styles.balanceValue}>
                  <span className={styles.balanceAmount}>{formatDuration(remainingSeconds)}</span>
                  <span className={styles.balanceSuffix}> available</span>
                </span>
              </div>
            ) : null}
            {accountLabel || onSignOut ? (
              <div className={styles.profileMenu} ref={menuRef}>
                <button
                  aria-expanded={menuOpen}
                  aria-haspopup="menu"
                  className={`${styles.profileTrigger} ${active === "account" ? styles.profileTriggerActive : ""}`}
                  type="button"
                  onClick={() => setMenuOpen((open) => !open)}
                >
                  <span className={styles.profileAvatar} aria-hidden="true">
                    {getInitials(accountLabel)}
                  </span>
                  <span className={styles.profileText}>Account</span>
                </button>

                {menuOpen ? (
                  <div className={styles.profilePopover} role="menu" aria-label="Account menu">
                    <div className={styles.profileSummary}>
                      <span className={styles.profileSummaryLabel}>Signed in as</span>
                      <span className={styles.profileSummaryValue}>{accountLabel ?? "Talven account"}</span>
                    </div>
                    <Link className={styles.profileAction} href="/app/account" onClick={() => setMenuOpen(false)}>
                      Account settings
                    </Link>
                    {onSignOut ? (
                      <button
                        className={`${styles.profileAction} ${styles.profileActionDanger}`}
                        role="menuitem"
                        type="button"
                        onClick={() => {
                          setMenuOpen(false);
                          onSignOut();
                        }}
                      >
                        Sign out
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </header>
  );
}
