import Link from "next/link";

import { packPlans, pricingCopy, subscriptionPlans } from "../content/pricing";
import styles from "./pricing.module.css";

export default function PricingPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.container}>
          <div className={styles.headerInner}>
            <Link href="/" className={styles.brand}>
              <span className={styles.brandMark} aria-hidden="true" />
              <span className={styles.brandText}>
                <span className={styles.brandMeta}>Private intelligence</span>
                <span className={styles.brandWord}>Talven</span>
              </span>
            </Link>
            <div className={styles.actions}>
              <Link href="/" className={`${styles.button} ${styles.buttonGhost}`}>
                Return to Talven
              </Link>
              <Link href="/signup" className={`${styles.button} ${styles.buttonPrimary}`}>
                Get your first briefing
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <div className={styles.heroIntro}>
            <p className={styles.eyebrow}>Pricing</p>
            <h1>Choose the access pattern that matches how you listen.</h1>
            <p>
              Use standing access when briefing is habitual. Use reserve packs when listening comes in concentrated
              bursts.
            </p>
          </div>

          <div className={styles.heroMeta}>
            <div className={styles.metaCard}>
              <span className={styles.metaLabel}>Standing access</span>
              <p className={styles.metaValue}>Lower cost per hour for regular listeners.</p>
            </div>
            <div className={styles.metaCard}>
              <span className={styles.metaLabel}>Reserve credits</span>
              <p className={styles.metaValue}>Measured flexibility when your listening comes in waves.</p>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <article className={styles.sectionCard}>
            <div className={styles.sectionLead}>
              <p className={styles.sectionLabel}>{pricingCopy.subscriptions.section_label}</p>
              <h2>{pricingCopy.subscriptions.headline}</h2>
              <p>{pricingCopy.subscriptions.subhead}</p>

              {pricingCopy.subscriptions.benefits ? (
                <ul className={styles.noteList}>
                  {pricingCopy.subscriptions.benefits.map((benefit) => (
                    <li key={benefit}>{benefit}</li>
                  ))}
                </ul>
              ) : null}

              <p className={styles.footnote}>{pricingCopy.subscriptions.footnote}</p>
            </div>

            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Monthly</th>
                    <th>Hours</th>
                    <th>Best for</th>
                  </tr>
                </thead>
                <tbody>
                  {subscriptionPlans.map((plan) => (
                    <tr key={plan.name} className={plan.highlight ? styles.rowHighlight : ""}>
                      <td>{plan.name}</td>
                      <td>{plan.price}</td>
                      <td>{plan.hours}</td>
                      <td>{plan.features[0]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className={styles.section}>
          <article className={styles.sectionCard}>
            <div className={styles.sectionLead}>
              <p className={styles.sectionLabel}>{pricingCopy.packs.section_label}</p>
              <h2>{pricingCopy.packs.headline}</h2>
              <p>{pricingCopy.packs.subhead}</p>

              <div className={styles.noteStack}>
                <div className={styles.noteCard}>
                  <span className={styles.noteLabel}>{pricingCopy.packs.notes_label}</span>
                  <p>{pricingCopy.packs.footnote}</p>
                </div>
                {pricingCopy.packs.footnoteMuted ? (
                  <div className={styles.noteCardMuted}>
                    <span className={styles.noteLabel}>Forward plan</span>
                    <p>{pricingCopy.packs.footnoteMuted}</p>
                  </div>
                ) : null}
              </div>
            </div>

            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Pack</th>
                    <th>Price</th>
                    <th>Hours</th>
                    <th>Designed for</th>
                  </tr>
                </thead>
                <tbody>
                  {packPlans.map((plan) => (
                    <tr key={plan.name} className={plan.highlight ? styles.rowHighlight : ""}>
                      <td>{plan.name}</td>
                      <td>{plan.price}</td>
                      <td>{plan.hours}</td>
                      <td>{plan.features[0]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className={styles.cta}>
          <h2>Need help choosing a plan?</h2>
          <p>Start with a free briefing. You can move into paid access once the habit and volume become clear.</p>
          <Link href="/signup" className={`${styles.button} ${styles.buttonPrimary}`}>
            Start with a free briefing
          </Link>
        </section>
      </main>
    </div>
  );
}
