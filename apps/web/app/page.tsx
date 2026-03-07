import Link from "next/link";

import HeroSection from "./components/landing/HeroSection";
import HowItWorksSection from "./components/landing/HowItWorksSection";
import PricingToggleSection from "./components/PricingToggleSection";
import ProblemSection from "./components/landing/ProblemSection";
import ProofSection from "./components/landing/ProofSection";
import QualitySection from "./components/landing/QualitySection";
import SmoothScrollLink from "./components/SmoothScrollLink";
import { landingContent } from "./content/landing";
import styles from "./page.module.css";

type HomePageProps = {
  searchParams: Promise<{
    pricing?: string | string[];
  }>;
};

export default async function Home({ searchParams }: HomePageProps) {
  const params = await searchParams;
  const pricingParam = Array.isArray(params.pricing) ? params.pricing[0] : params.pricing;
  const pricingMode = pricingParam === "packs" ? "packs" : "subscriptions";

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.container}>
          <div className={styles.navShell}>
            <Link href="/" className={styles.brand}>
              <span className={styles.brandMark} aria-hidden="true" />
              Fathom
            </Link>

            <nav className={styles.nav} aria-label="Main">
              {landingContent.nav.map((item) => (
                <SmoothScrollLink key={item.href} href={item.href}>
                  {item.label}
                </SmoothScrollLink>
              ))}
            </nav>

            <div className={styles.navActions}>
              <Link href="/signin" className={`${styles.button} ${styles.buttonGhost}`}>
                Sign in
              </Link>
              <Link href="/signup" className={`${styles.button} ${styles.buttonPrimary}`}>
                Start free
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main>
        <HeroSection content={landingContent.hero} />
        <ProblemSection content={landingContent.problem} />
        <HowItWorksSection content={landingContent.howItWorks} />
        <ProofSection content={landingContent.proof} />
        <QualitySection content={landingContent.quality} />

        <section id="pricing" className={styles.section} aria-labelledby="pricing-heading">
          <div className={styles.container}>
            <div className={styles.sectionIntro}>
              <p className={styles.eyebrow}>{landingContent.pricingIntro.eyebrow}</p>
              <h2 id="pricing-heading" className={styles.sectionTitle}>
                {landingContent.pricingIntro.title}
              </h2>
              <p className={styles.sectionSubtitle}>{landingContent.pricingIntro.subtitle}</p>
            </div>
            <PricingToggleSection mode={pricingMode} />
          </div>
        </section>

        <section id="faq" className={styles.sectionAlt} aria-labelledby="faq-heading">
          <div className={styles.container}>
            <div className={styles.sectionIntro}>
              <p className={styles.eyebrow}>{landingContent.faq.eyebrow}</p>
              <h2 id="faq-heading" className={styles.sectionTitle}>
                {landingContent.faq.title}
              </h2>
            </div>

            <div className={styles.faqList}>
              {landingContent.faq.items.map((item) => (
                <details key={item.question} className={styles.faqItem}>
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.ctaSection} aria-labelledby="final-cta-heading">
          <div className={styles.container}>
            <div className={styles.ctaInner}>
              <h2 id="final-cta-heading">{landingContent.finalCta.title}</h2>
              <p>{landingContent.finalCta.text}</p>
              <div className={styles.ctaActions}>
                <Link href={landingContent.finalCta.primaryCta.href} className={`${styles.button} ${styles.buttonPrimary}`}>
                  {landingContent.finalCta.primaryCta.label}
                </Link>
                <SmoothScrollLink href={landingContent.finalCta.secondaryCta.href} className={`${styles.button} ${styles.buttonGhost}`}>
                  {landingContent.finalCta.secondaryCta.label}
                </SmoothScrollLink>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.container}>
          <div className={styles.footerInner}>
            <span>{landingContent.footer.copyright}</span>
            <div className={styles.footerLinks}>
              {landingContent.footer.links.map((link) =>
                link.href.startsWith("/") ? (
                  <Link key={link.href} href={link.href}>
                    {link.label}
                  </Link>
                ) : (
                  <SmoothScrollLink key={link.href} href={link.href}>
                    {link.label}
                  </SmoothScrollLink>
                )
              )}
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
