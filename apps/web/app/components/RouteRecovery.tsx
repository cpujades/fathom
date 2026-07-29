"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { logger } from "../lib/logger";
import styles from "../resilience.module.css";

type RouteRecoveryProps = {
  description: string;
  error: Error & { digest?: string };
  homeHref: string;
  homeLabel: string;
  reset: () => void;
  scope: "app" | "global" | "route";
  title: string;
};

export function RouteRecovery({
  description,
  error,
  homeHref,
  homeLabel,
  reset,
  scope,
  title
}: RouteRecoveryProps) {
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    logger.error("web.route_boundary.rendered", {
      digest: error.digest,
      error_name: error.name,
      scope
    });
    headingRef.current?.focus();
  }, [error, scope]);

  return (
    <main id="main-content" className={styles.page}>
      <section className={styles.card} aria-labelledby="route-error-title">
        <p className={styles.kicker}>Talven</p>
        <h1 className={styles.title} id="route-error-title" ref={headingRef} tabIndex={-1}>
          {title}
        </h1>
        <p className={styles.copy}>{description}</p>
        <div className={styles.actions}>
          <button className={styles.primaryAction} type="button" onClick={reset}>
            Try again
          </button>
          <Link className={styles.secondaryAction} href={homeHref}>
            {homeLabel}
          </Link>
        </div>
      </section>
    </main>
  );
}
