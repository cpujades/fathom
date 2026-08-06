import type { BriefingSessionResponse } from "@fathom/api-client";
import { getBillingOffersAction } from "../../lib/usage.ts";

type SessionFailureSource = Pick<BriefingSessionResponse, "error_code" | "error_message"> | null;

export type FailurePresentation = {
  actionHref: string;
  actionLabel: string;
  description: string;
  detail: string;
  title: string;
};

export type LifecyclePresentation = {
  hint: string;
  label: string;
  status: string;
};

export function isBillingAdmissionErrorCode(code: string | null | undefined): boolean {
  return code === "insufficient_video_time" || code === "no_video_time" || code === "balance_blocked";
}

export function buildSameSourceRetryHref(sourceUrl: string | null | undefined): string {
  if (!sourceUrl) {
    return "/app";
  }
  return `/app/briefings/new?url=${encodeURIComponent(sourceUrl)}&confirm=retry`;
}

export function getFailurePresentation(
  session: SessionFailureSource,
  sessionLoadError: string | null,
  sessionLoadErrorCode: string | null = null,
  retrySourceUrl: string | null = null,
  hasActivePaidSubscription: boolean | null = null
): FailurePresentation {
  const code = session?.error_code ?? sessionLoadErrorCode ?? "";
  const rawMessage = session?.error_message ?? sessionLoadError ?? "";
  const normalizedMessage = rawMessage.toLowerCase();

  if (code === "not_found" || normalizedMessage.includes("not found")) {
    return {
      actionHref: "/app/briefings",
      actionLabel: "Back to briefings",
      title: "Briefing not found",
      description: "This briefing is no longer available in your library.",
      detail: "It may have been archived, or the link may be incomplete."
    };
  }

  if (isBillingAdmissionErrorCode(code)) {
    const billingAction = getBillingOffersAction(hasActivePaidSubscription);
    return {
      actionHref: billingAction.href,
      actionLabel: billingAction.label,
      title: code === "balance_blocked" ? "Briefing creation paused" : "More video time needed",
      description:
        code === "no_video_time"
          ? "No video time remains on this account."
          : code === "balance_blocked"
            ? "Outstanding video time must be repaid before another briefing can start."
            : "This source needs more video time than is currently available.",
      detail: "Add more video time, then start the briefing again."
    };
  }

  if (code === "provider_capacity_reached") {
    return {
      actionHref: buildSameSourceRetryHref(retrySourceUrl),
      actionLabel: "Try again",
      title: "Talven is handling high demand",
      description: "Your source is fine.",
      detail: "Please try again in a few minutes. Talven will wait for your confirmation before starting a new briefing."
    };
  }

  if (code === "provider_temporarily_unavailable") {
    return {
      actionHref: buildSameSourceRetryHref(retrySourceUrl),
      actionLabel: "Try again",
      title: "A service is temporarily unavailable",
      description: "Your source is fine.",
      detail: "Please try again in a few minutes. Talven will ask before starting a new briefing.",
    };
  }

  if (code === "usage_settlement_failed") {
    return {
      actionHref: "/app/briefings",
      actionLabel: "View your briefings",
      title: "Final account update pending",
      description: "The briefing was written, but Talven could not finish the account update.",
      detail: "Talven will keep retrying safely. Avoid starting a duplicate while finalization is pending."
    };
  }

  if (
    code === "invalid_request" ||
    code === "source_duration_unknown" ||
    code === "invalid_job_payload" ||
    code === "source_download_failed" ||
    normalizedMessage.includes("unsupported") ||
    normalizedMessage.includes("no audio streams") ||
    normalizedMessage.includes("youtube downloader") ||
    normalizedMessage.includes("download audio")
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Try another source",
      title: "Source not supported",
      description: "Talven could not read usable audio from this link.",
      detail: "Try a public YouTube URL. Private, unavailable, or audio-free videos cannot be briefed yet."
    };
  }

  if (
    code === "transcription_failed" ||
    normalizedMessage.includes("groq") ||
    normalizedMessage.includes("transcript") ||
    normalizedMessage.includes("transcription") ||
    normalizedMessage.includes("empty transcript")
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Start another briefing",
      title: "Transcript failed",
      description: "The source opened, but the audio could not be transcribed.",
      detail: "The audio service could not return a usable transcript. Try again in a moment or use another source."
    };
  }

  if (
    code === "summary_failed" ||
    normalizedMessage.includes("openrouter") ||
    normalizedMessage.includes("summary") ||
    normalizedMessage.includes("summar")
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Start another briefing",
      title: "Briefing failed",
      description: "The transcript was available, but the written briefing could not be completed.",
      detail: "The writing service did not return a usable briefing. Try again in a moment; if it repeats, contact support."
    };
  }

  if (
    code === "external_service_error" ||
    code === "rate_limit_exceeded" ||
    code === "not_ready"
  ) {
    return {
      actionHref: "/app",
      actionLabel: "Try again",
      title: "Service temporarily unavailable",
      description: "A service Talven relies on did not respond in time.",
      detail: "Your source is safe. Wait a moment, then try it again."
    };
  }

  if (code === "max_attempts_exceeded") {
    return {
      actionHref: "/app",
      actionLabel: "Start another briefing",
      title: "Briefing took too long",
      description: "Talven retried the job but could not finish it.",
      detail: "Try again later or use another source."
    };
  }

  if (code === "configuration_error") {
    return {
      actionHref: "/app/briefings",
      actionLabel: "Back to briefings",
      title: "Service configuration issue",
      description: "Talven could not complete this briefing because a required service is unavailable.",
      detail: "This needs an operator fix. The source was not the problem."
    };
  }

  return {
    actionHref: "/app",
    actionLabel: "Start another briefing",
    title: sessionLoadError ? "Could not open this briefing" : "Briefing stopped",
    description: sessionLoadError
      ? "Talven could not load the latest briefing details."
      : "Something interrupted the run before the final briefing was delivered.",
    detail: sessionLoadError
      ? "Check your connection and try opening it again."
      : "Try again in a moment or use another source."
  };
}

export function getDeliveryFailurePresentation(): FailurePresentation {
  return {
    actionHref: "/app/briefings",
    actionLabel: "Back to briefings",
    title: "Your briefing is ready",
    description: "Talven saved the finished briefing, but this reader could not load the text.",
    detail: "Try loading it again. This will not create another briefing or use more video time."
  };
}

export function getFinalizationPresentation(
  errorCode: string | null | undefined,
  fallbackLabel: string,
  fallbackHint: string
): LifecyclePresentation {
  if (errorCode === "usage_settlement_failed") {
    return {
      label: "Finalizing account usage",
      hint: "Your briefing is written. Talven is safely retrying the final account update.",
      status: "Retrying"
    };
  }

  return {
    label: fallbackLabel,
    hint: fallbackHint,
    status: "Live"
  };
}

export function buildMarkdownFilename(sourceTitle: string | null | undefined): string {
  const stem = (sourceTitle ?? "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72);

  return `${stem || "talven-briefing"}.md`;
}
