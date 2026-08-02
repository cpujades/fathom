import Image from "next/image";
import Link from "next/link";

import type { BriefingSessionResponse } from "@fathom/api-client";

import chrome from "../../components/app-chrome";
import { getLifecycleStepDescription, LIFECYCLE_STEPS } from "./sessionLifecycle";
import type { SessionUiPhase, StreamHealth } from "./sessionState";
import styles from "./session-hero.module.css";

type BriefingSessionHeroProps = {
  connectionNotice: string | null;
  exportNotice: string | null;
  failureActionHref: string;
  failureActionLabel: string;
  failureDetail: string;
  hasTopActions: boolean;
  headline: string;
  heroEyebrow: string;
  isDeliveryFailed: boolean;
  isFailed: boolean;
  isLoadFailed: boolean;
  isReady: boolean;
  lifecycleHint: string;
  lifecycleKicker: string;
  lifecycleStatusLabel: string;
  lifecycleStepIndex: number;
  lifecycleTitle: string;
  longRunningNotice: string | null;
  onDownloadMarkdown: () => void;
  onOpenPdf: () => void;
  onRetry: () => void;
  pdfError: string | null;
  pdfLoading: boolean;
  pdfUrl: string | null;
  phase: SessionUiPhase;
  primaryPdfActionLabel: string;
  rawMarkdown: string;
  session: BriefingSessionResponse | null;
  sessionLoadError: string | null;
  showCreditCta: boolean;
  showHeroTopline: boolean;
  showLifecyclePanel: boolean;
  sourceActionLabel: string;
  sourceDurationLabel: string | null;
  sourceLabel: string;
  sourceUrl: string;
  streamHealth: StreamHealth;
  subhead: string;
};

export function BriefingSessionHero({
  connectionNotice,
  exportNotice,
  failureActionHref,
  failureActionLabel,
  failureDetail,
  hasTopActions,
  headline,
  heroEyebrow,
  isDeliveryFailed,
  isFailed,
  isLoadFailed,
  isReady,
  lifecycleHint,
  lifecycleKicker,
  lifecycleStatusLabel,
  lifecycleStepIndex,
  lifecycleTitle,
  longRunningNotice,
  onDownloadMarkdown,
  onOpenPdf,
  onRetry,
  pdfError,
  pdfLoading,
  pdfUrl,
  phase,
  primaryPdfActionLabel,
  rawMarkdown,
  session,
  sessionLoadError,
  showCreditCta,
  showHeroTopline,
  showLifecyclePanel,
  sourceActionLabel,
  sourceDurationLabel,
  sourceLabel,
  sourceUrl,
  streamHealth,
  subhead
}: BriefingSessionHeroProps) {
  return (
    <section className={`${chrome.heroBlock} ${styles.sessionHero}`}>
      <div className={styles.sessionHeroGrid}>
        <div className={styles.heroSourceMedia}>
          <div className={styles.heroThumbnailFrame}>
            {session?.source_thumbnail_url ? (
              <Image className={styles.heroThumbnail} src={session.source_thumbnail_url} alt="" fill sizes="160px" priority />
            ) : (
              <div className={styles.sourceThumbnailFallback}><span>{sourceLabel}</span></div>
            )}
          </div>
        </div>

        <div className={styles.heroCopy}>
          {showHeroTopline ? (
            <div className={styles.heroTopline}>
              {heroEyebrow ? <p className={chrome.heroEyebrow}>{heroEyebrow}</p> : null}
              <div className={chrome.heroMeta}>
                {isFailed ? <span className={chrome.statusPillDanger}>Failed</span> : null}
                {isLoadFailed || isDeliveryFailed ? <span className={chrome.statusPillWarning}>Unavailable</span> : null}
              </div>
            </div>
          ) : null}
          <h1 className={styles.sessionTitle}>{headline}</h1>
          <div className={styles.sourceMetaLine}>
            {session?.source_author ? <span>By {session.source_author}</span> : null}
            {sourceDurationLabel ? <span>{sourceDurationLabel}</span> : null}
          </div>
          {subhead ? <p className={styles.sessionDeck}>{subhead}</p> : null}
        </div>
      </div>

      {isLoadFailed || isDeliveryFailed ? (
        <div className={styles.errorCard} role="alert">
          <p>{failureDetail}</p>
          <div className={chrome.actionRow}>
            <button className={chrome.primaryButton} type="button" onClick={onRetry}>
              {isDeliveryFailed ? "Load briefing again" : "Try opening again"}
            </button>
            <Link className={chrome.secondaryButton} href={failureActionHref}>{failureActionLabel}</Link>
          </div>
        </div>
      ) : null}

      {showLifecyclePanel ? (
        <div className={styles.lifecyclePanel} aria-live="polite">
          <div className={styles.lifecycleHeader}>
            <div>
              <p className={styles.lifecycleKicker}>{lifecycleKicker}</p>
              <h2>{lifecycleTitle}</h2>
              <p>{lifecycleHint}</p>
            </div>
            <span className={`${chrome.statusPillMuted} ${streamHealth === "reconnecting" ? styles.lifecycleWarningPill : styles.liveStatus}`}>
              {lifecycleStatusLabel}
            </span>
          </div>

          <div className={styles.lifecycleSteps} aria-label="Briefing progress">
            {LIFECYCLE_STEPS.map((step, index) => (
              <div
                className={getLifecycleStepClassName(index, lifecycleStepIndex)}
                key={step.label}
                aria-current={index === lifecycleStepIndex ? "step" : undefined}
              >
                <span aria-hidden="true" />
                <div>
                  <p>{step.label}</p>
                  <small>
                    {getLifecycleStepDescription({
                      index,
                      phase,
                      state: session?.state ?? null,
                      step,
                      activeIndex: lifecycleStepIndex
                    })}
                    {index === lifecycleStepIndex ? <span className={styles.lifecycleEllipsis} aria-hidden="true" /> : null}
                  </small>
                </div>
              </div>
            ))}
          </div>

          {longRunningNotice ? <div className={styles.statusNoticeCard} role="status"><p>{longRunningNotice}</p></div> : null}
          {connectionNotice ? <div className={styles.connectionCard} role="status"><p>{connectionNotice}</p></div> : null}
          {sessionLoadError ? (
            <div className={styles.errorCard} role="alert">
              <p>{sessionLoadError}</p>
              {showCreditCta ? <div className={chrome.actionRow}><Link className={chrome.primaryButton} href="/app/billing#billing-offers">Get more video time</Link></div> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {hasTopActions ? (
        <div className={styles.heroActionBar}>
          {pdfUrl ? (
            <a className={`${chrome.primaryButton} ${styles.heroPdfAction}`} href={pdfUrl} target="_blank" rel="noreferrer">Download PDF</a>
          ) : (
            <button className={`${chrome.primaryButton} ${styles.heroPdfAction}`} type="button" onClick={onOpenPdf} disabled={pdfLoading || !session?.briefing_id}>
              {primaryPdfActionLabel}
            </button>
          )}
          <div className={styles.heroUtilityLinks}>
            {isReady && rawMarkdown ? <button className={styles.textActionLink} type="button" onClick={onDownloadMarkdown}>Download Markdown</button> : null}
            {sourceUrl ? <a className={styles.textActionLink} href={sourceUrl} target="_blank" rel="noreferrer">{sourceActionLabel}</a> : null}
            <Link className={`${styles.textActionLink} ${styles.newBriefingLink}`} href="/app">Start another briefing</Link>
          </div>
        </div>
      ) : null}
      {pdfError ? <p className={`${chrome.inlineStatus} ${chrome.inlineStatusError}`} role="alert">{pdfError}</p> : null}
      {exportNotice ? <p className={chrome.inlineStatus} role="status">{exportNotice}</p> : null}
    </section>
  );
}

function getLifecycleStepClassName(index: number, activeIndex: number): string {
  return [
    styles.lifecycleStep,
    index < activeIndex ? styles.lifecycleStepComplete : "",
    index === activeIndex ? styles.lifecycleStepActive : ""
  ].filter(Boolean).join(" ");
}
