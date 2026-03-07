const DEFAULT_NEXT_PATH = "/app";
const ALLOWED_NEXT_PATHS = new Set(["/app", "/app/billing"]);

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
    if (!ALLOWED_NEXT_PATHS.has(parsed.pathname)) {
      return fallback;
    }

    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
};

export const buildAuthCallbackUrl = (nextPath?: string): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const callbackUrl = new URL("/auth/callback", getSiteUrl());

  if (safeNextPath !== DEFAULT_NEXT_PATH) {
    callbackUrl.searchParams.set("next", safeNextPath);
  }

  return callbackUrl.toString();
};
