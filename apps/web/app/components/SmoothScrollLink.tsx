"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { MouseEvent, ReactNode } from "react";

type SmoothScrollLinkProps = {
  href: string;
  className?: string;
  children: ReactNode;
  onClick?: () => void;
};

const SCROLL_OFFSET = 92;
const SCROLL_DURATION_MS = 880;

const easeInOutQuart = (progress: number): number => {
  return progress < 0.5 ? 8 * progress * progress * progress * progress : 1 - Math.pow(-2 * progress + 2, 4) / 2;
};

const animateScrollTo = (targetY: number) => {
  const startY = window.scrollY;
  const distance = targetY - startY;
  const startedAt = performance.now();

  const step = (currentTime: number) => {
    const elapsed = currentTime - startedAt;
    const progress = Math.min(elapsed / SCROLL_DURATION_MS, 1);
    const easedProgress = easeInOutQuart(progress);

    window.scrollTo(0, startY + distance * easedProgress);

    if (progress < 1) {
      window.requestAnimationFrame(step);
    }
  };

  window.requestAnimationFrame(step);
};

export default function SmoothScrollLink({ href, className, children, onClick }: SmoothScrollLinkProps) {
  const router = useRouter();
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

    const targetTop = target.getBoundingClientRect().top + window.scrollY - SCROLL_OFFSET;
    const targetY = Math.max(targetTop, 0);

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      window.scrollTo(0, targetY);
    } else {
      animateScrollTo(targetY);
    }

    const currentQuery = searchParams.toString();
    const nextUrl = `${pathname}${currentQuery ? `?${currentQuery}` : ""}${href}`;

    router.replace(nextUrl, { scroll: false });
    window.history.replaceState(window.history.state, "", nextUrl);
  };

  return (
    <a href={href} className={className} onClick={handleClick}>
      {children}
    </a>
  );
}
