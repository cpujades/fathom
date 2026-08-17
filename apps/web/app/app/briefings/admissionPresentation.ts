import type { ApiErrorDetails } from "../../lib/apiErrors.ts";
import { formatExactDuration } from "../../lib/format.ts";
import { getBillingOffersAction, type BillingOffersAction } from "../../lib/usage.ts";

export type AdmissionFailurePresentation = {
  billingAction: BillingOffersAction | null;
  description: string;
  detail: string;
  retryLabel: string;
  title: string;
};

function formatDurationLimit(seconds: number): string {
  if (seconds > 0 && seconds % 3_600 === 0) {
    const hours = seconds / 3_600;
    return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  return formatExactDuration(seconds);
}

export function getAdmissionFailurePresentation(
  code: string | null,
  message: string,
  details: ApiErrorDetails | null,
  hasActivePaidSubscription: boolean | null
): AdmissionFailurePresentation {
  if (code === "insufficient_video_time") {
    const required = details?.required_seconds;
    const available = details?.available_seconds;
    const comparison =
      required !== undefined && available !== undefined
        ? `This video needs ${formatExactDuration(required)}, but ${formatExactDuration(available)} are available.`
        : "This video needs more time than is currently available.";
    return {
      billingAction: getBillingOffersAction(hasActivePaidSubscription),
      title: "More video time needed",
      description: comparison,
      detail: "Add video time or replace the URL with a shorter public YouTube video.",
      retryLabel: "Try this source again"
    };
  }

  if (code === "no_video_time") {
    return {
      billingAction: getBillingOffersAction(hasActivePaidSubscription),
      title: "No video time remains",
      description: "Your current video-time balance is zero.",
      detail: "Add video time before starting this briefing, or keep the source here for later.",
      retryLabel: "Check this source again"
    };
  }

  if (code === "balance_blocked") {
    const debt = details?.debt_seconds;
    return {
      billingAction: getBillingOffersAction(hasActivePaidSubscription),
      title: "Briefing creation paused",
      description:
        debt !== undefined
          ? `${formatExactDuration(debt)} of new video time must repay the outstanding balance first.`
          : "New video time must repay the outstanding balance first.",
      detail: "Add video time to clear the outstanding balance before trying this source again.",
      retryLabel: "Check this source again"
    };
  }

  if (code === "active_job_limit_reached") {
    const maximum = details?.maximum_active_jobs;
    return {
      billingAction: null,
      title: "Briefings already in progress",
      description:
        maximum !== undefined
          ? `Talven can process up to ${maximum} briefings for one account at a time.`
          : "This account already has the maximum number of briefings in progress.",
      detail: "Wait for one briefing to finish, then try this source again.",
      retryLabel: "Check again"
    };
  }

  if (code === "video_time_committed") {
    const required = details?.required_seconds;
    const available = details?.available_seconds;
    const pending = details?.pending_seconds;
    const comparison =
      required !== undefined && available !== undefined
        ? `This video needs ${formatExactDuration(required)}, but ${formatExactDuration(available)} remain after current jobs.`
        : "Briefings in progress have committed part of the available video time.";
    return {
      billingAction: getBillingOffersAction(hasActivePaidSubscription),
      title: "Video time is already committed",
      description: comparison,
      detail:
        pending !== undefined
          ? `${formatExactDuration(pending)} are committed to briefings in progress. Wait for one to finish, add video time, or choose a shorter source.`
          : "Wait for one briefing to finish, add video time, or choose a shorter source.",
      retryLabel: "Check again"
    };
  }

  if (code === "source_duration_unknown") {
    return {
      billingAction: null,
      title: "Video length unavailable",
      description: "Talven cannot safely calculate how much video time this source needs.",
      detail: "Try another public YouTube video whose complete duration is available.",
      retryLabel: "Try another source"
    };
  }

  if (code === "source_too_long") {
    const maximum = details?.maximum_seconds;
    return {
      billingAction: null,
      title: "Video is too long",
      description: maximum !== undefined
        ? `Talven supports videos up to ${formatDurationLimit(maximum)}.`
        : "This video is longer than Talven's supported limit.",
      detail: "Choose a shorter public YouTube video to start a briefing.",
      retryLabel: "Try another source"
    };
  }

  if (code === "invalid_request") {
    return {
      billingAction: null,
      title: "Source not supported",
      description: "Talven needs a readable public YouTube video URL.",
      detail: message,
      retryLabel: "Try another source"
    };
  }

  return {
    billingAction: null,
    title: "Could not start the briefing",
    description: "Talven could not finish checking this request.",
    detail: message,
    retryLabel: "Try again"
  };
}
