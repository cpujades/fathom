import { getOptionalPublicUrlEnv } from "@fathom/api-client/publicEnv";

const DEFAULT_NEXT_PATH = "/app";
const DEFAULT_SITE_URL = "http://localhost:3000";
const AUTH_PLAN_PATTERN = /^[a-z0-9]+(?:[_-][a-z0-9]+)*$/;
const MAX_AUTH_PLAN_LENGTH = 64;
const PUBLIC_BRIEFING_PATH_PATTERN = /^\/b\/[0-9a-f]{32}$/;

type AuthIntent = "paid";

type AuthIntentContext = {
  intent?: string | null;
  plan?: string | null;
};

type SafeAuthIntentContext = {
  intent: AuthIntent | null;
  plan: string | null;
};

const isAllowedNextPathname = (pathname: string): boolean => {
  return (
    pathname === DEFAULT_NEXT_PATH ||
    pathname.startsWith(`${DEFAULT_NEXT_PATH}/`) ||
    pathname === "/explore" ||
    PUBLIC_BRIEFING_PATH_PATTERN.test(pathname)
  );
};

export const getSiteUrl = (): string => {
  const configuredSiteUrl = getOptionalPublicUrlEnv("NEXT_PUBLIC_SITE_URL", process.env.NEXT_PUBLIC_SITE_URL);
  if (configuredSiteUrl) {
    const parsed = new URL(configuredSiteUrl);
    if (
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      throw new Error("Invalid NEXT_PUBLIC_SITE_URL. Set an exact origin without credentials, a path, query, or fragment.");
    }
    if (
      process.env.NODE_ENV === "production" &&
      parsed.protocol !== "https:" &&
      parsed.hostname !== "localhost" &&
      !parsed.hostname.endsWith(".localhost")
    ) {
      throw new Error("Invalid NEXT_PUBLIC_SITE_URL. Hosted production origins must use https.");
    }
    return parsed.origin;
  }

  if (typeof window !== "undefined") {
    return window.location.origin;
  }

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "Missing NEXT_PUBLIC_SITE_URL. Set the exact public frontend origin for a hosted build."
    );
  }

  return DEFAULT_SITE_URL;
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

export const getSafeAuthIntentContext = (context?: AuthIntentContext): SafeAuthIntentContext => {
  const intent = context?.intent === "paid" ? context.intent : null;
  const candidatePlan = context?.plan?.trim().toLowerCase() ?? "";
  const plan =
    intent && candidatePlan.length <= MAX_AUTH_PLAN_LENGTH && AUTH_PLAN_PATTERN.test(candidatePlan)
      ? candidatePlan
      : null;

  return {
    intent,
    plan
  };
};

export const buildAuthDestinationPath = (
  nextPath?: string,
  context?: AuthIntentContext
): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const safeContext = getSafeAuthIntentContext(context);
  if (!safeContext.intent) {
    return safeNextPath;
  }

  const destinationUrl = new URL(safeNextPath, "http://localhost");
  destinationUrl.searchParams.set("intent", safeContext.intent);
  if (safeContext.plan) {
    destinationUrl.searchParams.set("plan", safeContext.plan);
  } else {
    destinationUrl.searchParams.delete("plan");
  }
  return `${destinationUrl.pathname}${destinationUrl.search}${destinationUrl.hash}`;
};

const buildAuthEntryPath = (
  pathname: "/signin" | "/signup",
  nextPath?: string,
  context?: AuthIntentContext
): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const safeContext = getSafeAuthIntentContext(context);
  const targetUrl = new URL(pathname, "http://localhost");

  if (safeNextPath !== DEFAULT_NEXT_PATH) {
    targetUrl.searchParams.set("next", safeNextPath);
  }

  if (safeContext.intent) {
    targetUrl.searchParams.set("intent", safeContext.intent);
  }
  if (safeContext.plan) {
    targetUrl.searchParams.set("plan", safeContext.plan);
  }

  return `${targetUrl.pathname}${targetUrl.search}`;
};

export const buildSignInPath = (
  nextPath?: string,
  context?: AuthIntentContext
): string => {
  return buildAuthEntryPath("/signin", nextPath, context);
};

export const buildSignUpPath = (
  nextPath?: string,
  context?: AuthIntentContext
): string => {
  return buildAuthEntryPath("/signup", nextPath, context);
};

export const buildAuthCallbackUrl = (
  nextPath?: string,
  context?: AuthIntentContext
): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const safeContext = getSafeAuthIntentContext(context);
  const callbackUrl = new URL("/auth/callback", getSiteUrl());

  if (safeNextPath !== DEFAULT_NEXT_PATH) {
    callbackUrl.searchParams.set("next", safeNextPath);
  }
  if (safeContext.intent) {
    callbackUrl.searchParams.set("intent", safeContext.intent);
  }
  if (safeContext.plan) {
    callbackUrl.searchParams.set("plan", safeContext.plan);
  }

  return callbackUrl.toString();
};

export const buildPasswordRecoveryCallbackUrl = (nextPath?: string): string => {
  const safeNextPath = getSafeNextPath(nextPath, DEFAULT_NEXT_PATH);
  const callbackUrl = new URL("/auth/recovery/callback", getSiteUrl());

  if (safeNextPath !== DEFAULT_NEXT_PATH) {
    callbackUrl.searchParams.set("next", safeNextPath);
  }

  return callbackUrl.toString();
};

export const getCurrentAppPath = (fallback = DEFAULT_NEXT_PATH): string => {
  if (typeof window === "undefined") {
    return fallback;
  }

  return getSafeNextPath(`${window.location.pathname}${window.location.search}${window.location.hash}`, fallback);
};

export type { AuthIntentContext, SafeAuthIntentContext };
