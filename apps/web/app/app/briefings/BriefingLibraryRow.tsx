import Image from "next/image";
import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";

import type { BriefingListItem } from "../../lib/briefings";
import { formatDateTime, formatExactDuration } from "../../lib/format";
import chrome from "../../components/app-chrome";
import styles from "./briefing-row.module.css";

type BriefingLibraryRowProps = {
  confirmingDelete: boolean;
  deleting: boolean;
  entry: BriefingListItem;
  opening: boolean;
  onCancelDelete: () => void;
  onDelete: () => void;
  onOpen: (event: MouseEvent<HTMLAnchorElement>) => void;
  onPrefetch: () => void;
  onRequestDelete: () => void;
  setRemoveButtonRef: (node: HTMLButtonElement | null) => void;
};

export function BriefingLibraryRow({
  confirmingDelete,
  deleting,
  entry,
  opening,
  onCancelDelete,
  onDelete,
  onOpen,
  onPrefetch,
  onRequestDelete,
  setRemoveButtonRef
}: BriefingLibraryRowProps) {
  const entryState = getBriefingState(entry);
  const stateLabel = getBriefingStateLabel(entryState);
  const actionLabel = opening ? "Opening" : getBriefingActionLabel(entry);

  return (
    <article className={styles.libraryRow}>
      <div className={styles.libraryRowBody}>
        <div className={styles.libraryRowMain}>
          <div className={styles.libraryTopRow}>
            <div className={styles.libraryMedia}>
              <div className={styles.libraryThumbnailFrame}>
                {entry.source_thumbnail_url ? (
                  <Image
                    className={styles.libraryThumbnail}
                    src={entry.source_thumbnail_url}
                    alt=""
                    fill
                    sizes="(max-width: 420px) 84px, (max-width: 720px) 96px, 96px"
                  />
                ) : (
                  <div className={styles.libraryThumbnailFallback}>
                    <span>{getSourceTypeLabel(entry.source_type)}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className={styles.libraryRowContent}>
            <div className={styles.libraryTitleBlock}>
              <div className={styles.titleRow}>
                <BriefingLink entry={entry} onOpen={onOpen} onPrefetch={onPrefetch} className={styles.libraryTitleLink}>
                  {entry.title}
                </BriefingLink>
                {stateLabel ? (
                  <span className={`${styles.libraryStatePill} ${entryState === "failed" ? styles.libraryStatePillFailed : styles.libraryStatePillActive}`}>
                    {stateLabel}
                  </span>
                ) : null}
              </div>

              <div className={styles.metaRow}>
                <span className={styles.metaDate}>{formatDateTime(entry.created_at)}</span>
                {entry.author ? <span className={styles.metaAuthor}>By {entry.author}</span> : null}
                {entry.source_duration_seconds ? (
                  <span className={styles.metaDuration}>{formatExactDuration(entry.source_duration_seconds)}</span>
                ) : null}
              </div>
            </div>

            <div className={styles.rowActions}>
              <div className={styles.actionSet}>
                <BriefingLink
                  entry={entry}
                  onOpen={onOpen}
                  onPrefetch={onPrefetch}
                  className={`${chrome.primaryButton} ${styles.libraryPrimaryAction}`}
                >
                  {actionLabel}
                </BriefingLink>
                <a className={`${chrome.ghostButton} ${styles.librarySecondaryAction}`} href={entry.source_url} target="_blank" rel="noreferrer">
                  {getSourceActionLabel(entry.source_type)}
                </a>
                {!confirmingDelete ? (
                  <button className={styles.menuDangerAction} type="button" onClick={onRequestDelete} ref={setRemoveButtonRef}>
                    Remove
                  </button>
                ) : null}
              </div>

              {confirmingDelete ? (
                <div className={styles.confirmBlock} role="group" aria-label={`Remove ${entry.title}`}>
                  <p className={styles.confirmText}>Remove this briefing from history?</p>
                  <div className={styles.confirmActions}>
                    <button autoFocus className={styles.confirmCancelButton} type="button" onClick={onCancelDelete}>
                      Keep briefing
                    </button>
                    <button className={styles.dangerButton} type="button" onClick={onDelete} disabled={deleting}>
                      {deleting ? "Removing…" : "Remove from history"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

function BriefingLink({
  children,
  className,
  entry,
  onOpen,
  onPrefetch
}: {
  children: ReactNode;
  className: string;
  entry: BriefingListItem;
  onOpen: (event: MouseEvent<HTMLAnchorElement>) => void;
  onPrefetch: () => void;
}) {
  return (
    <Link
      className={className}
      href={entry.session_path}
      onClick={onOpen}
      onMouseEnter={onPrefetch}
      onPointerDown={onPrefetch}
      onFocus={onPrefetch}
    >
      {children}
    </Link>
  );
}

export function isBriefingProcessing(entry: BriefingListItem): boolean {
  const state = getBriefingState(entry);
  return state !== "ready" && state !== "failed";
}

function getSourceTypeLabel(sourceType: BriefingListItem["source_type"]): string {
  if (sourceType === "youtube") return "YouTube";
  if (sourceType === "url") return "Web";
  return "Source";
}

function getSourceActionLabel(sourceType: BriefingListItem["source_type"]): string {
  return sourceType === "youtube" ? "Video" : "Source";
}

function getBriefingState(entry: BriefingListItem): BriefingListItem["state"] {
  return entry.state ?? "ready";
}

function getBriefingStateLabel(state: BriefingListItem["state"]): string | null {
  if (state === "ready") return null;
  if (state === "failed") return "Needs review";
  if (state === "accepted") return "Starting";
  if (state === "resolving_source" || state === "reusing_existing") return "Checking";
  if (state === "transcribing") return "Transcribing";
  if (state === "drafting_briefing") return "Writing";
  return "Saving";
}

function getBriefingActionLabel(entry: BriefingListItem): string {
  if (getBriefingState(entry) === "failed") return "Review";
  return isBriefingProcessing(entry) ? "Progress" : "Open";
}
