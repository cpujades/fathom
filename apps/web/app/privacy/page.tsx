import type { Metadata } from "next";
import Link from "next/link";

import styles from "../legal.module.css";

export const metadata: Metadata = {
  title: "Privacy Policy | Talven",
  description: "How Talven handles account, billing, and briefing data."
};

export default function PrivacyPage() {
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
          <p className={styles.eyebrow}>Privacy</p>
          <h1 className={styles.title}>Privacy policy</h1>
          <p className={styles.lede}>
            Talven turns user-submitted YouTube podcast links into private written briefings. This policy explains the
            data we collect, why we collect it, and how to contact us about privacy requests.
          </p>
          <p className={styles.updated}>Last updated: May 16, 2026</p>

          <section className={styles.section}>
            <h2>Information we collect</h2>
            <p>We collect the information needed to run Talven and support your account:</p>
            <ul>
              <li>Account details such as email address, name, authentication state, and account preferences.</li>
              <li>Briefing inputs such as submitted YouTube URLs and generated briefing content.</li>
              <li>Usage and billing details such as listening balance, plan, purchases, refunds, and payment status.</li>
              <li>Technical information such as device, browser, request metadata, logs, and error diagnostics.</li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>How we use information</h2>
            <p>We use information to authenticate users, create and store briefings, process billing, prevent abuse, fix errors, and improve the product experience.</p>
          </section>

          <section className={styles.section}>
            <h2>Service providers</h2>
            <p>
              Talven relies on trusted providers for authentication, storage, billing, transcription, summarization, and
              infrastructure. These providers process information only as needed to deliver the product.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Your choices</h2>
            <p>
              You can manage your account from the app, cancel paid access through billing controls when available, and
              contact us to request account or data assistance.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Contact</h2>
            <p>
              For privacy questions or requests, email{" "}
              <a href="mailto:contact@talven.ai">contact@talven.ai</a>.
            </p>
          </section>
        </article>
      </main>

      <footer className={styles.footer}>
        <span>Copyright 2026 Talven</span>
        <nav className={styles.footerLinks} aria-label="Legal navigation">
          <Link href="/">Home</Link>
          <Link href="/terms">Terms</Link>
          <a href="mailto:contact@talven.ai">Contact</a>
        </nav>
      </footer>
    </div>
  );
}
