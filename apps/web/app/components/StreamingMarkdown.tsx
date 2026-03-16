"use client";

import { useEffect, useRef, useState } from "react";
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
  const frameRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isStreaming) {
      const frameId = window.requestAnimationFrame(() => {
        setDisplayedMarkdown(markdown);
      });
      return () => {
        window.cancelAnimationFrame(frameId);
      };
    }

    if (!displayedMarkdown || markdown.length < displayedMarkdown.length || !markdown.startsWith(displayedMarkdown)) {
      const frameId = window.requestAnimationFrame(() => {
        setDisplayedMarkdown(markdown);
      });
      return () => {
        window.cancelAnimationFrame(frameId);
      };
    }

    if (markdown.length === displayedMarkdown.length) {
      return;
    }

    const animate = (timestamp: number) => {
      const lastTimestamp = lastFrameTimeRef.current ?? timestamp;
      const elapsedMs = Math.max(timestamp - lastTimestamp, 16);
      lastFrameTimeRef.current = timestamp;

      setDisplayedMarkdown((current) => {
        if (!current || markdown.length <= current.length || !markdown.startsWith(current)) {
          return markdown;
        }

        const remaining = markdown.length - current.length;
        const charsPerSecond = 90 + Math.min(remaining * 6, 540);
        const nextLength = Math.min(current.length + Math.max(1, Math.floor((charsPerSecond * elapsedMs) / 1000)), markdown.length);

        return markdown.slice(0, nextLength);
      });

      frameRef.current = window.requestAnimationFrame(animate);
    };

    frameRef.current = window.requestAnimationFrame(animate);

    return () => {
      lastFrameTimeRef.current = null;
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
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
