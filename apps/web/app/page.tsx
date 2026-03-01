import Link from "next/link";

import PricingSection from "./components/PricingSection";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <header className={`${styles.header} max-w-7xl mx-auto px-4 md:px-6 lg:px-8`}>
        <div className="flex items-center gap-2">
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true" />
            Fathom
          </div>
        </div>
        <nav className={`${styles.nav} hidden md:flex`}>
          <a href="#how">How it works</a>
          <a href="#signal">Signal</a>
          <a href="#pricing">Pricing</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className={`${styles.actions} hidden md:flex`}>
          <Link className={`${styles.button} ${styles.buttonGhost}`} href="/signin">
            Sign in
          </Link>
          <Link className={`${styles.button} ${styles.buttonPrimary}`} href="/signup">
            Get started
          </Link>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 md:px-6 lg:px-8">
        <section className={styles.hero}>
          <div className={`${styles.reveal} ${styles.revealDelay1}`}>
            <div className={`${styles.pill} ${styles.pillSpaced}`}>Podcast intelligence</div>
            <h1 className={styles.heroTitle}>
              Fathom the signal. Skip the noise.
            </h1>
            <p className={styles.heroText}>
              Turn any podcast or YouTube link into a high-signal briefing in seconds. Stay
              informed, without the backlog.
            </p>
            <div className={styles.heroActions}>
              <Link className={`${styles.button} ${styles.buttonPrimary}`} href="/signup">
                Start free
              </Link>
              <Link className={`${styles.button} ${styles.buttonGhost}`} href="#signal">
                See a sample
              </Link>
            </div>
          </div>
          <div className={`${styles.heroCard} ${styles.reveal} ${styles.revealDelay2}`}>
            <div className={styles.heroCardHeader}>
              <span className={styles.heroCardTitle}>
                Dwarkesh Patel - Andrej Karpathy: We&rsquo;re summoning ghosts, not building animals
              </span>
              <span className={styles.pill}>96% complete</span>
            </div>
            <div className={styles.heroList}>
              <div>
                <strong>Core thesis:</strong> Powerful learning loops beat raw hours. Structured
                reflection is the multiplier.
              </div>
              <div>
                <strong>Key moments:</strong> 4 frameworks, 11 timestamped insights, and a
                distilled reading list.
              </div>
              <div>
                <strong>Actionables:</strong> Three experiments to run next week.
              </div>
            </div>
          </div>
        </section>

        <section className={`${styles.section} ${styles.reveal}`} id="how">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>From link to briefing in seconds</h2>
            <p className={styles.sectionText}>
              Fathom turns long-form audio into clean, structured intelligence, ready for
              skimming, sharing, and saving.
            </p>
          </div>
          <div className={styles.workflow}>
            {[
              {
                title: "Drop a link",
                text: "Paste any podcast or YouTube URL. We handle the audio, transcription, and structure."
              },
              {
                title: "Track the build",
                text: "Watch progress in real time with live updates and clear status cues."
              },
              {
                title: "Save the signal",
                text: "Export to PDF, keep a clean archive, and revisit insights anytime."
              }
            ].map((step, index) => (
              <div key={step.title} className={styles.card}>
                <div className={styles.stepNumber}>Step {index + 1}</div>
                <h3 className={styles.cardTitle}>{step.title}</h3>
                <p className={styles.cardText}>{step.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className={`${styles.section} ${styles.reveal}`} id="signal">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Everything you need, nothing you don&rsquo;t</h2>
            <p className={styles.sectionText}>
              Structured summaries keep the insight density high: key takeaways, quotes,
              frameworks, and recommended next actions.
            </p>
          </div>
          <div className={styles.demo}>
            <div className={styles.demoPanel}>
              <h3 className={styles.cardTitle}>Signal Brief</h3>
              <div className={styles.demoList}>
                <div>- 12-minute read time, auto-generated chapters</div>
                <div>- Source-linked notes with timestamps</div>
                <div>- TL;DR + deep dive summaries</div>
                <div>- Export to PDF or Markdown</div>
              </div>
            </div>
            <div className={styles.demoPanel}>
              <h3 className={styles.cardTitle}>Smart Archive</h3>
              <div className={styles.demoList}>
                <div>- Keep a searchable library of episodes</div>
                <div>- Resume where you left off across devices</div>
                <div>- Highlights you can share instantly</div>
                <div>- Coming soon: ask questions about episodes</div>
              </div>
            </div>
          </div>
        </section>

        <section className={`${styles.section} ${styles.reveal}`}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>Built for serious listeners</h2>
            <p className={styles.sectionText}>
              Quietly powerful. Designed for professionals who value clarity, speed, and a clean
              workflow.
            </p>
          </div>
          <div className={styles.grid3}>
            {[
              {
                title: "Accuracy-first",
                text: "Multi-pass summaries tuned for high precision and minimal fluff."
              },
              {
                title: "Real-time feedback",
                text: "Progress updates keep you in the loop while the summary is built."
              },
              {
                title: "Export-ready",
                text: "PDF briefings formatted for reading, printing, and sharing."
              }
            ].map((item) => (
              <div key={item.title} className={styles.card}>
                <h3 className={styles.cardTitle}>{item.title}</h3>
                <p className={styles.cardText}>{item.text}</p>
              </div>
            ))}
          </div>
        </section>

        <PricingSection className={`${styles.section} ${styles.reveal}`} />

        <section className={`${styles.section} ${styles.reveal}`} id="faq">
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>FAQ</h2>
            <p className={styles.sectionText}>Answers to the big questions.</p>
          </div>
          <div className={styles.faq}>
            <div className={styles.faqItem}>
              <h3 className={styles.cardTitle}>Does it work with YouTube?</h3>
              <p className={styles.cardText}>
                Yes. Paste a YouTube link and Fathom will handle the audio extraction and
                summarize it.
              </p>
            </div>
            <div className={styles.faqItem}>
              <h3 className={styles.cardTitle}>Can I export and share summaries?</h3>
              <p className={styles.cardText}>
                You&rsquo;ll get clean Markdown and a PDF export for every completed job.
              </p>
            </div>
            <div className={styles.faqItem}>
              <h3 className={styles.cardTitle}>How accurate is the summary?</h3>
              <p className={styles.cardText}>
                We focus on high-signal outputs with multiple passes for structure and clarity.
              </p>
            </div>
          </div>
        </section>

        <section className={`${styles.section} ${styles.reveal}`}>
          <div className={styles.demoPanel}>
            <div className={styles.sectionHeader}>
              <h2 className={styles.sectionTitle}>Ready to clear your backlog?</h2>
              <p className={styles.sectionText}>
                Get your first briefing in seconds. No commitment required.
              </p>
            </div>
            <div className={styles.heroActions}>
              <Link className={`${styles.button} ${styles.buttonPrimary}`} href="/signup">
                Start free
              </Link>
              <Link className={`${styles.button} ${styles.buttonGhost}`} href="/signin">
                Sign in
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div>Copyright 2026 Fathom. All rights reserved.</div>
        <a href="mailto:contact@fathom.ai">contact@fathom.ai</a>
      </footer>
    </div>
  );
}
