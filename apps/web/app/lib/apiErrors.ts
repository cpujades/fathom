import type { ApiErrorBody } from "@fathom/api-client";

export type ApiErrorDetails = {
  available_seconds?: number;
  debt_seconds?: number;
  maximum_seconds?: number;
  required_seconds?: number;
};

const getApiErrorMessage = (error: ApiErrorBody | unknown, fallback: string): string => {
  if (!error || typeof error !== "object") {
    return fallback;
  }

  if ("error" in error) {
    const detail = (error as { error?: { message?: string } }).error;
    if (detail?.message) {
      return detail.message;
    }
  }

  if ("detail" in error) {
    const detail = (error as { detail?: Array<{ msg?: string }> }).detail;
    if (Array.isArray(detail) && detail[0]?.msg) {
      return detail[0].msg;
    }
  }

  if ("message" in error && typeof (error as { message?: string }).message === "string") {
    return (error as { message?: string }).message ?? fallback;
  }

  return fallback;
};

const getApiErrorCode = (error: ApiErrorBody | unknown): string | null => {
  if (!error || typeof error !== "object" || !("error" in error)) {
    return null;
  }

  const code = (error as { error?: { code?: unknown } }).error?.code;
  return typeof code === "string" && code.trim() ? code : null;
};

const getApiErrorDetails = (error: ApiErrorBody | unknown): ApiErrorDetails | null => {
  if (!error || typeof error !== "object" || !("error" in error)) {
    return null;
  }

  const value = (error as { error?: { details?: unknown } }).error?.details;
  if (!value || typeof value !== "object") {
    return null;
  }

  const raw = value as Record<string, unknown>;
  const details: ApiErrorDetails = {};
  for (const key of ["available_seconds", "debt_seconds", "maximum_seconds", "required_seconds"] as const) {
    const item = raw[key];
    if (typeof item === "number" && Number.isFinite(item) && item >= 0) {
      details[key] = Math.floor(item);
    }
  }
  return Object.keys(details).length > 0 ? details : null;
};

export { getApiErrorCode, getApiErrorDetails, getApiErrorMessage };
