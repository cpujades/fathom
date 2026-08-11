import Image from "next/image";
import Link from "next/link";
import type { MouseEvent, ReactNode } from "react";
import { ExternalLink } from "lucide-react";

import type { BriefingListItem } from "../../lib/briefings";
import { formatDateTime, formatExactDuration } from "../../lib/format";
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
  const visibleStateLabel = opening ? "Opening" : stateLabel;

  return (
    <article className={styles.libraryRow}>
      <div className={styles.libraryRowBody}>
        <div className={styles.libraryRowMain}>
          <div className={styles.libraryTopRow}>
            <div className={styles.libraryMedia}>
              <BriefingLink
                ariaLabel={`Open ${entry.title}`}
                entry={entry}
                onOpen={onOpen}
                onPrefetch={onPrefetch}
                className={styles.libraryThumbnailLink}
              >
                <span className={styles.libraryThumbnailFrame}>
                  {entry.source_thumbnail_url ? (
                    <Image
                      className={styles.libraryThumbnail}
                      src={entry.source_thumbnail_url}
                      alt=""
                      fill
                      sizes="(max-width: 420px) 84px, (max-width: 720px) 96px, 96px"
                    />
                  ) : (
                    <span className={styles.libraryThumbnailFallback}>
                      <span>{getSourceTypeLabel(entry.source_type)}</span>
                    </span>
                  )}
                </span>
              </BriefingLink>
            </div>
          </div>

          <div className={styles.libraryRowContent}>
            <div className={styles.libraryTitleBlock}>
              <div className={styles.titleRow}>
                <BriefingLink entry={entry} onOpen={onOpen} onPrefetch={onPrefetch} className={styles.libraryTitleLink}>
                  {entry.title}
                </BriefingLink>
                {visibleStateLabel ? (
                  <span className={`${styles.libraryStatePill} ${entryState === "failed" ? styles.libraryStatePillFailed : styles.libraryStatePillActive}`}>
                    {visibleStateLabel}
                  </span>
                ) : null}
              </div>

              <div className={styles.metaRow}>
                <span className={styles.metaDate}>{formatDateTime(entry.created_at)}</span>
                {entry.author ? <span className={styles.metaAuthor}>By {entry.author}</span> : null}
                {entry.source_duration_seconds ? (
                  <span className={styles.metaDuration}>{formatExactDuration(entry.source_duration_seconds)}</span>
                ) : null}
                <a className={styles.librarySourceLink} href={entry.source_url} target="_blank" rel="noreferrer">
                  <ExternalLink aria-hidden="true" size={13} strokeWidth={1.9} />
                  {getSourceActionLabel(entry.source_type)}
                </a>
              </div>
            </div>

            <div className={styles.rowActions}>
              {!confirmingDelete ? (
                <button className={styles.menuDangerAction} type="button" onClick={onRequestDelete} ref={setRemoveButtonRef}>
                  Archive
                </button>
              ) : null}

              {confirmingDelete ? (
                <div className={styles.confirmBlock} role="group" aria-label={`Archive ${entry.title}`}>
                  <p className={styles.confirmText}>
                    Archive this briefing? It will leave your library, but submitting the same source restores it.
                  </p>
                  <div className={styles.confirmActions}>
                    <button autoFocus className={styles.confirmCancelButton} type="button" onClick={onCancelDelete}>
                      Keep briefing
                    </button>
                    <button className={styles.dangerButton} type="button" onClick={onDelete} disabled={deleting}>
                      {deleting ? "Archiving…" : "Archive briefing"}
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
  ariaLabel,
  children,
  className,
  entry,
  onOpen,
  onPrefetch
}: {
  ariaLabel?: string;
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
      aria-label={ariaLabel}
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
  return sourceType === "youtube" ? "Original video" : "Original source";
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
