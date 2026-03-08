"use client";

import { usePathname, useSearchParams } from "next/navigation";
import type { MouseEvent, ReactNode } from "react";

type SmoothScrollLinkProps = {
  href: string;
  className?: string;
  children: ReactNode;
  onClick?: () => void;
};

const SCROLL_OFFSET = 92;
const CENTER_ALIGNMENT_PADDING = 24;

export default function SmoothScrollLink({ href, className, children, onClick }: SmoothScrollLinkProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.();

    if (!href.startsWith("#")) {
      return;
    }

    event.preventDefault();

    const target = document.querySelector<HTMLElement>(href);
    if (!target) {
      return;
    }

    const targetRect = target.getBoundingClientRect();
    const absoluteTop = targetRect.top + window.scrollY;
    const targetY =
      target.dataset.scrollAlign === "center"
        ? Math.max(absoluteTop - (window.innerHeight - targetRect.height) / 2 - CENTER_ALIGNMENT_PADDING, 0)
        : Math.max(absoluteTop - SCROLL_OFFSET, 0);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      window.scrollTo(0, targetY);
    } else {
      window.scrollTo({
        top: targetY,
        behavior: "smooth"
      });
    }

    const currentQuery = searchParams.toString();
    const nextUrl = `${pathname}${currentQuery ? `?${currentQuery}` : ""}${href}`;

    window.history.replaceState(window.history.state, "", nextUrl);
  };

  return (
    <a href={href} className={className} onClick={handleClick}>
      {children}
    </a>
  );
}
