"use client";

import { useEffect, useState } from "react";
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
  const [displayedMarkdown, setDisplayedMarkdown] = useState(markdown);

  useEffect(() => {
    if (!isStreaming) {
      return;
    }

    let timeoutId: number | null = null;
    if (!displayedMarkdown || markdown.length < displayedMarkdown.length || !markdown.startsWith(displayedMarkdown)) {
      timeoutId = window.setTimeout(() => {
        setDisplayedMarkdown(markdown);
      }, 0);
      return () => {
        if (timeoutId !== null) {
          window.clearTimeout(timeoutId);
        }
      };
    }

    if (markdown.length === displayedMarkdown.length) {
      return;
    }

    timeoutId = window.setTimeout(() => {
      setDisplayedMarkdown((current) => {
        if (!current || markdown.length <= current.length || !markdown.startsWith(current)) {
          return markdown;
        }

        const remaining = markdown.length - current.length;
        const step = Math.min(Math.max(Math.ceil(remaining / 10), 20), 120);
        return markdown.slice(0, current.length + step);
      });
    }, 32);

    return () => {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [displayedMarkdown, isStreaming, markdown]);

  const renderedMarkdown = isStreaming ? displayedMarkdown : markdown;

  if (!renderedMarkdown && !isStreaming) {
    return null;
  }

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{renderedMarkdown}</ReactMarkdown>
      {isStreaming ? <span className={cursorClassName} aria-hidden="true" /> : null}
    </div>
  );
}
