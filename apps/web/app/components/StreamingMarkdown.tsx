"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface StreamingMarkdownProps {
  markdown: string;
  isStreaming?: boolean;
  className?: string;
  cursorClassName?: string;
}

export function StreamingMarkdown({
  markdown,
  isStreaming = false,
  className,
  cursorClassName
}: StreamingMarkdownProps) {
  if (!markdown && !isStreaming) {
    return null;
  }

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      {isStreaming ? <span className={cursorClassName} aria-hidden="true" /> : null}
    </div>
  );
}
