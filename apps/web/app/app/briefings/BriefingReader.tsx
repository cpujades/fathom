import Image from "next/image";
import Link from "next/link";
import { ArrowUp } from "lucide-react";

import type { BriefingSessionResponse } from "@fathom/api-client";

import { StreamingMarkdown } from "../../components/StreamingMarkdown";
import chrome from "../../components/app-chrome";
import {
  emphasizeFirstSentence,
  getMobileSectionLabel,
  getSectionDisplayTitle,
  getSectionKind,
  type ParsedBriefing,
  type ParsedBriefingSection
} from "./briefingMarkdown";
import contentStyles from "./session-content.module.css";
import readerStyles from "./session-reader.module.css";
import type { TakeawayItem } from "./takeawayParser";

const styles = { ...contentStyles, ...readerStyles };

type NavigationSection = { id: string; label: string };

type BriefingReaderProps = {
  actionError: string | null;
  connectionNotice: string | null;
  deleteConfirming: boolean;
  deleteLoading: boolean;
  failureActionHref: string;
  failureActionLabel: string;
  failureDetail: string;
  isFailed: boolean;
  isReady: boolean;
  isStreaming: boolean;
  markdownToRender: string;
  mobileNavigationSections: NavigationSection[];
  navigationSections: NavigationSection[];
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
  onOpenPdf: () => void;
  onRequestDelete: () => void;
  parsedBriefing: ParsedBriefing;
  pdfLoading: boolean;
  pdfUrl: string | null;
  primaryPdfActionLabel: string;
  readingProgress: number;
  session: BriefingSessionResponse | null;
  showNowReading: boolean;
  showLifecyclePanel: boolean;
  takeawayItems: TakeawayItem[];
};

export function BriefingReader({
  actionError,
  connectionNotice,
  deleteConfirming,
  deleteLoading,
  failureActionHref,
  failureActionLabel,
  failureDetail,
  isFailed,
  isReady,
  isStreaming,
  markdownToRender,
  mobileNavigationSections,
  navigationSections,
  onCancelDelete,
  onConfirmDelete,
  onOpenPdf,
  onRequestDelete,
  parsedBriefing,
  pdfLoading,
  pdfUrl,
  primaryPdfActionLabel,
  readingProgress,
  session,
  showNowReading,
  showLifecyclePanel,
  takeawayItems
}: BriefingReaderProps) {
  return (
    <section className={styles.briefingLayout}>
      {mobileNavigationSections.length ? (
        <nav className={styles.mobileReaderBar} aria-label="Reader shortcuts">
          <div className={styles.mobileReaderLinks}>
            {mobileNavigationSections.map((section) => (
              <a href={`#${section.id}`} key={section.id}>
                {getMobileSectionLabel(section.label)}
              </a>
            ))}
          </div>
          {isReady ? (
            pdfUrl ? (
              <a className={styles.mobileReaderAction} href={pdfUrl} target="_blank" rel="noreferrer">
                PDF
              </a>
            ) : (
              <button
                className={styles.mobileReaderAction}
                type="button"
                onClick={onOpenPdf}
                disabled={pdfLoading || !session?.briefing_id}
              >
                {pdfLoading ? "PDF..." : "PDF"}
              </button>
            )
          ) : null}
        </nav>
      ) : null}

      <article className={styles.briefingReader}>
        {connectionNotice && !showLifecyclePanel ? (
          <div className={styles.connectionCard} role="status">
            <p>{connectionNotice}</p>
          </div>
        ) : null}

        {parsedBriefing.summary ? (
          <section className={`${chrome.surfaceStrong} ${styles.summaryPanel}`} id="briefing-summary">
            <p className={styles.sectionKicker}>Brief in 30 seconds</p>
            <StreamingMarkdown
              markdown={emphasizeFirstSentence(parsedBriefing.summary)}
              className={`${styles.markdown} ${styles.summaryMarkdown}`}
            />
          </section>
        ) : null}

        {parsedBriefing.takeaways ? (
          <section className={`${chrome.surface} ${styles.takeawayPanel}`} id="briefing-takeaways">
            <div className={styles.sectionHeader}>
              <p className={styles.sectionKicker}>What matters</p>
              <h2 className={styles.sectionTitle}>Key takeaways</h2>
            </div>
            {takeawayItems.length > 1 ? (
              <ol className={styles.takeawayGrid}>
                {takeawayItems.map((takeaway, index) => (
                  <li className={styles.takeawayCard} key={`${takeaway.title}-${index}`}>
                    <h3>{takeaway.title}</h3>
                    <StreamingMarkdown
                      markdown={takeaway.bodyMarkdown}
                      className={`${styles.markdown} ${styles.takeawayBody}`}
                    />
                  </li>
                ))}
              </ol>
            ) : (
              <StreamingMarkdown
                markdown={parsedBriefing.takeaways}
                className={`${styles.markdown} ${styles.takeawayMarkdown}`}
              />
            )}
          </section>
        ) : null}

        {parsedBriefing.articleSections.length ? (
          <div className={styles.articleStack}>
            {parsedBriefing.articleSections.map((section) => (
              <BriefingContentSection section={section} key={section.id} />
            ))}
          </div>
        ) : markdownToRender && !parsedBriefing.summary && !parsedBriefing.takeaways ? (
          <section className={`${chrome.surface} ${styles.articleSection}`}>
            <StreamingMarkdown
              markdown={markdownToRender}
              isStreaming={isStreaming}
              className={styles.markdown}
              cursorClassName={styles.streamingCursor}
            />
          </section>
        ) : (
          <p className={chrome.emptyState}>
            {isFailed
              ? "We could not render the briefing. Start a new one when you are ready."
              : "Your briefing will appear here as soon as Talven has content ready."}
          </p>
        )}

        {parsedBriefing.references ? (
          <section className={`${chrome.surfaceMuted} ${styles.referenceSection}`} id={parsedBriefing.references.id}>
            <details>
              <summary>Sources and references</summary>
              <StreamingMarkdown markdown={parsedBriefing.references.content} className={styles.markdown} />
            </details>
          </section>
        ) : null}
      </article>

      <aside className={styles.briefingSide}>
        {navigationSections.length > 2 ? (
          <nav className={`${chrome.readerSideCard} ${styles.contentsCard}`} aria-label="Briefing sections">
            <a
              className={`${styles.nowReading} ${showNowReading ? styles.nowReadingVisible : ""}`}
              href="#briefing-hero"
              aria-hidden={!showNowReading}
              aria-label={`Back to the top of ${parsedBriefing.title}`}
              tabIndex={showNowReading ? undefined : -1}
            >
              <span className={styles.nowReadingMedia}>
                {session?.source_thumbnail_url ? (
                  <Image
                    className={styles.nowReadingThumbnail}
                    src={session.source_thumbnail_url}
                    alt=""
                    fill
                    sizes="42px"
                  />
                ) : (
                  <span className={styles.nowReadingFallback} aria-hidden="true">T</span>
                )}
              </span>
              <span className={styles.nowReadingCopy}>
                <span>Now reading</span>
                <strong>{parsedBriefing.title}</strong>
              </span>
              <ArrowUp className={styles.nowReadingTopIcon} aria-hidden="true" size={15} strokeWidth={1.9} />
            </a>
            <div className={styles.contentsHeader}>
              <h2 className={chrome.surfaceTitle}>Contents</h2>
              <span>{readingProgress}% read</span>
            </div>
            <div className={styles.contentsProgressTrack} aria-hidden="true">
              <div className={styles.contentsProgressFill} style={{ width: `${readingProgress}%` }} />
            </div>
            <div className={styles.contentsList}>
              {navigationSections.map((section) => (
                <a href={`#${section.id}`} key={section.id}>
                  {section.label}
                </a>
              ))}
            </div>
          </nav>
        ) : null}

        <ReaderActions
          deleteConfirming={deleteConfirming}
          deleteLoading={deleteLoading}
          isReady={isReady}
          onCancelDelete={onCancelDelete}
          onConfirmDelete={onConfirmDelete}
          onRequestDelete={onRequestDelete}
        />

        {isFailed ? (
          <div className={styles.errorCard} role="alert">
            <p>{failureDetail}</p>
            {failureActionHref ? (
              <div className={chrome.actionRow}>
                <Link className={chrome.primaryButton} href={failureActionHref}>
                  {failureActionLabel}
                </Link>
              </div>
            ) : null}
          </div>
        ) : null}
        {actionError ? (
          <div className={styles.errorCard} role="alert">
            <p>{actionError}</p>
          </div>
        ) : null}
      </aside>

      <footer className={styles.briefingFooter}>
        <div className={styles.footerPrimaryRow}>
          {isReady ? (
            pdfUrl ? (
              <a className={styles.footerPdfAction} href={pdfUrl} target="_blank" rel="noreferrer">
                Download PDF
              </a>
            ) : (
              <button
                className={styles.footerPdfAction}
                type="button"
                onClick={onOpenPdf}
                disabled={pdfLoading || !session?.briefing_id}
              >
                {primaryPdfActionLabel}
              </button>
            )
          ) : null}
        </div>
        <div className={styles.footerNavigationRow}>
          <Link className={styles.textActionLink} href="/app/briefings">Back to briefings</Link>
          <Link className={styles.textActionLink} href="/app">Start another briefing</Link>
        </div>
        {isReady && !deleteConfirming ? (
          <div className={styles.footerDangerRow}>
            <DeleteTrigger disabled={deleteLoading} onClick={onRequestDelete} />
          </div>
        ) : null}
        {isReady && deleteConfirming ? (
          <div className={styles.footerDeleteConfirm} role="group" aria-label="Archive briefing">
            <span>Archive this briefing? Submitting the same source restores it.</span>
            <button className={styles.textActionLink} data-remove-cancel type="button" onClick={onCancelDelete} disabled={deleteLoading}>Cancel</button>
            <button className={`${styles.textActionLink} ${styles.removeTextButton}`} type="button" onClick={onConfirmDelete} disabled={deleteLoading}>
              {deleteLoading ? "Archiving..." : "Archive"}
            </button>
          </div>
        ) : null}
      </footer>
    </section>
  );
}

function BriefingContentSection({ section }: { section: ParsedBriefingSection }) {
  const sectionKind = getSectionKind(section.title);
  const sectionClassName = [
    chrome.surface,
    styles.articleSection,
    sectionKind === "deepRead" ? styles.deepReadSection : ""
  ].filter(Boolean).join(" ");
  const markdownClassName = [styles.markdown, sectionKind === "deepRead" ? styles.deepReadMarkdown : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={sectionClassName} id={section.id}>
      <h2 className={styles.articleSectionTitle}>{getSectionDisplayTitle(section.title, sectionKind)}</h2>
      <StreamingMarkdown markdown={section.content} className={markdownClassName} />
    </section>
  );
}

function ReaderActions({
  deleteConfirming,
  deleteLoading,
  isReady,
  onCancelDelete,
  onConfirmDelete,
  onRequestDelete
}: Pick<
  BriefingReaderProps,
  | "deleteConfirming"
  | "deleteLoading"
  | "isReady"
  | "onCancelDelete"
  | "onConfirmDelete"
  | "onRequestDelete"
>) {
  return (
    <div className={styles.desktopActionCard}>
      <Link className={styles.textActionLink} href="/app/briefings">Back to briefings</Link>
      <Link className={styles.textActionLink} href="/app">Start another briefing</Link>
      {isReady && !deleteConfirming ? <DeleteTrigger disabled={deleteLoading} onClick={onRequestDelete} /> : null}
      {isReady && deleteConfirming ? (
        <div className={styles.sidebarDeleteConfirm} role="group" aria-label="Archive briefing">
          <p>Archive this briefing? Submitting the same source restores it.</p>
          <div className={styles.sidebarDeleteActions}>
            <button className={styles.textActionLink} data-remove-cancel type="button" onClick={onCancelDelete} disabled={deleteLoading}>Cancel</button>
            <button className={`${styles.textActionLink} ${styles.removeTextButton}`} type="button" onClick={onConfirmDelete} disabled={deleteLoading}>
              {deleteLoading ? "Archiving..." : "Archive"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DeleteTrigger({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button className={`${styles.textActionLink} ${styles.removeTextButton}`} data-remove-trigger type="button" onClick={onClick} disabled={disabled}>
      Archive briefing
    </button>
  );
}
