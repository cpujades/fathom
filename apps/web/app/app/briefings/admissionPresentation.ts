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
        ? `Talven supports videos up to ${formatExactDuration(maximum)}.`
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
