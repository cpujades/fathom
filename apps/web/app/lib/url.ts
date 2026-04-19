const DEFAULT_NEXT_PATH = "/app";

const isAllowedNextPathname = (pathname: string): boolean => {
  return pathname === DEFAULT_NEXT_PATH || pathname.startsWith(`${DEFAULT_NEXT_PATH}/`);
};

export const getSiteUrl = (): string => {
  if (process.env.NEXT_PUBLIC_SITE_URL) {
    return process.env.NEXT_PUBLIC_SITE_URL;
  }

  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  return "http://localhost:3000";
};

export const getSafeNextPath = (candidate: string | null | undefined, fallback = DEFAULT_NEXT_PATH): string => {
  if (!candidate) {
    return fallback;
  }

  if (!candidate.startsWith("/") || candidate.startsWith("//")) {
    return fallback;
  }

  try {
    const parsed = new URL(candidate, "http://localhost");
    if (!isAllowedNextPathname(parsed.pathname)) {
      return fallback;
    }

    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
};

const buildAuthEntryPath = (
  pathname: "/signin" | "/signup",
  nextPath?: string,
  extraParams?: Record<string, string | null | undefined>
): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const targetUrl = new URL(pathname, "http://localhost");

  if (safeNextPath !== DEFAULT_NEXT_PATH) {
    targetUrl.searchParams.set("next", safeNextPath);
  }

  for (const [key, value] of Object.entries(extraParams ?? {})) {
    if (value) {
      targetUrl.searchParams.set(key, value);
    }
  }

  return `${targetUrl.pathname}${targetUrl.search}`;
};

export const buildSignInPath = (
  nextPath?: string,
  extraParams?: Record<string, string | null | undefined>
): string => {
  return buildAuthEntryPath("/signin", nextPath, extraParams);
};

export const buildSignUpPath = (
  nextPath?: string,
  extraParams?: Record<string, string | null | undefined>
): string => {
  return buildAuthEntryPath("/signup", nextPath, extraParams);
};

export const buildAuthCallbackUrl = (nextPath?: string): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const callbackUrl = new URL("/auth/callback", getSiteUrl());

  if (safeNextPath !== DEFAULT_NEXT_PATH) {
    callbackUrl.searchParams.set("next", safeNextPath);
  }

  return callbackUrl.toString();
};
