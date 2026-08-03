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
            Talven turns user-submitted public YouTube links into written briefings in an account-scoped library. This
            policy explains the data we collect, why we collect it, and how to contact us about privacy requests.
          </p>
          <p className={styles.updated}>Last updated: August 3, 2026</p>

          <section className={styles.section}>
            <h2>Information we collect</h2>
            <p>We collect the information needed to run Talven and support your account:</p>
            <ul>
              <li>Account details such as email address, name, authentication state, and account preferences.</li>
              <li>Briefing inputs such as submitted YouTube URLs and generated briefing content.</li>
              <li>Usage and billing details such as video-time balance, plan, purchases, refunds, and payment status.</li>
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
              Talven uses Supabase for authentication, database records, and private file storage; Groq for audio
              transcription; OpenRouter for briefing generation; and Polar for checkout, subscription, and refund
              processing. We also retrieve the public YouTube source you submit. Polar does not receive your source
              audio or briefing text.
            </p>
          </section>

          <section className={styles.section}>
            <h2>How source data moves</h2>
            <p>
              Talven temporarily stores downloaded source audio in private storage while Groq transcribes it. Talven tries
              to remove that temporary audio when processing finishes, although a service or storage failure may delay the
              cleanup. The transcript is then sent to OpenRouter to create the briefing. We may keep transcripts and
              briefings so the same compatible public video does not always need to be processed again. Two accounts may
              therefore receive the same stored processing result for the same public source. Their jobs, library state,
              usage, and billing remain separate, and one account cannot see another account&apos;s private activity.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Retention and deletion</h2>
            <p>
              Archiving a briefing removes it from your library view; it does not permanently erase it. Talven has not yet set a
              single deletion timetable because account, payment, security, and reusable processing records may need
              different rules. Contact us if you want us to review the information connected to your account or help with
              an account or data request.
            </p>
          </section>

          <section className={styles.section}>
            <h2>Your choices</h2>
            <p>
              You can manage your account from the app, use the billing portal for subscription controls, request eligible
              pack refunds through the product, and contact us for account or data assistance.
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
