import type { Metadata } from "next";
import Link from "next/link";

import styles from "../legal.module.css";

export const metadata: Metadata = {
  title: "Terms of Service | Talven",
  description: "The terms that apply when using Talven private podcast briefings."
};

export default function TermsPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          <span className={styles.brandMark} aria-hidden="true" />
          <span>Talven</span>
        </Link>
      </header>

      <main id="main-content" className={styles.main}>
        <article className={styles.article}>
          <p className={styles.eyebrow}>Terms</p>
          <h1 className={styles.title}>Terms of service</h1>
          <p className={styles.lede}>
            These terms describe the basic rules for using Talven. By creating an account or using the service, you agree
            to use Talven responsibly and only with sources you have the right to process.
          </p>
          <p className={styles.updated}>Last updated: May 16, 2026</p>

          <section className={styles.section}>
            <h2>Using Talven</h2>
            <p>
              Talven creates written briefings from supported public YouTube podcast URLs. You are responsible for the
              links you submit and for how you use, store, share, or rely on generated briefings.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Generated briefings</h2>
            <p>
              Briefings are generated from source material and may contain mistakes, omissions, or imperfect
              interpretation. Review important claims against the original source before relying on them for decisions.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Accounts and billing</h2>
            <p>
              You are responsible for maintaining access to your account. Paid plans, credit packs, refunds, renewals,
              and cancellations are handled through Talven billing flows and the payment provider shown during checkout.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Acceptable use</h2>
            <p>Do not use Talven to abuse the service, bypass usage limits, process unlawful material, or interfere with infrastructure or other users.</p>
          </section>

          <section className={styles.section}>
            <h2>Availability</h2>
            <p>
              We aim to keep Talven reliable, but the service may change, pause, or become unavailable due to maintenance,
              provider outages, or product updates.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Contact</h2>
            <p>
              For terms, billing, or product questions, email{" "}
              <a href="mailto:contact@talven.ai">contact@talven.ai</a>.
            </p>
          </section>
        </article>
      </main>

      <footer className={styles.footer}>
        <span>Copyright 2026 Talven</span>
        <nav className={styles.footerLinks} aria-label="Legal navigation">
          <Link href="/">Home</Link>
          <Link href="/privacy">Privacy</Link>
          <a href="mailto:contact@talven.ai">Contact</a>
        </nav>
      </footer>
    </div>
  );
}
