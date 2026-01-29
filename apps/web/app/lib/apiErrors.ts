import type { ApiErrorBody } from "@fathom/api-client";

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

export { getApiErrorMessage };
