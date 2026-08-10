import { Clipboard } from "lucide-react";

import styles from "./markdown-export-actions.module.css";

type MarkdownExportActionsProps = {
  copying: boolean;
  downloadClassName: string;
  onCopy: () => void;
  onDownload: () => void;
};

export function MarkdownExportActions({
  copying,
  downloadClassName,
  onCopy,
  onDownload
}: MarkdownExportActionsProps) {
  return (
    <div className={styles.actions} aria-label="Markdown export actions">
      <button
        className={styles.copyButton}
        type="button"
        onClick={onCopy}
        disabled={copying}
        aria-busy={copying}
        aria-label={copying ? "Copying Markdown" : "Copy Markdown"}
        title="Copy Markdown"
      >
        <Clipboard aria-hidden="true" size={18} strokeWidth={1.9} />
      </button>
      <button className={downloadClassName} type="button" onClick={onDownload}>
        Download Markdown
      </button>
    </div>
  );
}
