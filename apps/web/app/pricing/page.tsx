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
              Fathom
            </Link>
            <div className={styles.actions}>
              <Link href="/" className={`${styles.button} ${styles.buttonGhost}`}>
                Back to home
              </Link>
              <Link href="/signup" className={`${styles.button} ${styles.buttonPrimary}`}>
                Start free
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>Pricing</p>
          <h1>Clear pricing for recurring and one-time usage.</h1>
          <p>Use subscriptions for steady volume or packs for occasional high-intensity listening cycles.</p>
        </section>

        <section className={styles.section}>
          <h2>{pricingCopy.subscriptions.headline}</h2>
          <p>{pricingCopy.subscriptions.subhead}</p>

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

          <p className={styles.footnote}>{pricingCopy.subscriptions.footnote}</p>
        </section>

        <section className={styles.section}>
          <h2>{pricingCopy.packs.headline}</h2>
          <p>{pricingCopy.packs.subhead}</p>

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

          <p className={styles.footnote}>{pricingCopy.packs.footnote}</p>
        </section>

        <section className={styles.cta}>
          <h2>Need help choosing a plan?</h2>
          <p>Start free first. You can upgrade or switch billing style as your usage pattern becomes clear.</p>
          <Link href="/signup" className={`${styles.button} ${styles.buttonPrimary}`}>
            Create account
          </Link>
        </section>
      </main>
    </div>
  );
}
