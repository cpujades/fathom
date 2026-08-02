import type { BriefingSessionResponse } from "@fathom/api-client";

export type BriefingSessionState = BriefingSessionResponse["state"];

export const STATE_LABELS: Record<BriefingSessionState, string> = {
  accepted: "Starting",
  resolving_source: "Checking source",
  reusing_existing: "Checking library",
  transcribing: "Transcribing audio",
  drafting_briefing: "Writing briefing",
  finalizing_briefing: "Saving briefing",
  ready: "Ready",
  failed: "Needs attention"
};

export const STATE_HINTS: Record<BriefingSessionState, string> = {
  accepted: "Source received.",
  resolving_source: "Reading the page and looking for usable audio.",
  reusing_existing: "Checking your library before doing new work.",
  transcribing: "Turning audio into text.",
  drafting_briefing: "Shaping the transcript into a reader.",
  finalizing_briefing: "Saving the finished version.",
  ready: "Ready to read, export, or revisit later.",
  failed: "The run stopped before delivery completed."
};

export type LifecycleStep = {
  activeText: string;
  beforeText: string;
  completeText: string;
  label: string;
  states: BriefingSessionState[];
};

export const LIFECYCLE_STEPS: LifecycleStep[] = [
  {
    activeText: "Reading the source.",
    beforeText: "Waiting for source.",
    completeText: "Source locked.",
    label: "Check source",
    states: ["accepted", "resolving_source", "reusing_existing"]
  },
  {
    activeText: "Listening closely.",
    beforeText: "Waiting for source.",
    completeText: "Transcript ready.",
    label: "Transcribe",
    states: ["transcribing"]
  },
  {
    activeText: "Writing the briefing.",
    beforeText: "Waiting for transcript.",
    completeText: "Briefing written.",
    label: "Write",
    states: ["drafting_briefing"]
  },
  {
    activeText: "Saving the briefing.",
    beforeText: "Waiting for writing.",
    completeText: "Ready to read.",
    label: "Ready",
    states: ["finalizing_briefing", "ready"]
  }
];

const STILL_NORMAL_SECONDS = 30;
const LONG_SOURCE_SECONDS = 60;
const LONG_WAIT_SECONDS = 120;
const LEAVE_AND_RETURN_SECONDS = 300;
const POSSIBLY_STUCK_SECONDS = 600;

export function getLongRunningNotice(state: BriefingSessionState | null, elapsedSeconds: number): string | null {
  if (!state || state === "ready" || state === "failed" || elapsedSeconds < STILL_NORMAL_SECONDS) {
    return null;
  }
  if (elapsedSeconds >= POSSIBLY_STUCK_SECONDS) {
    return "This is taking much longer than expected. You can leave and return from Briefings, or try again later if it never finishes.";
  }
  if (elapsedSeconds >= LEAVE_AND_RETURN_SECONDS) {
    return "Still working. This is longer than normal, but longer sources can take several minutes. You can return from Briefings.";
  }
  if (elapsedSeconds >= LONG_WAIT_SECONDS) {
    return "Still working. This is taking a little longer than usual, especially if the source is long.";
  }
  if (elapsedSeconds >= LONG_SOURCE_SECONDS) {
    return "Still moving. Longer sources can take a minute or two before the briefing starts to appear.";
  }
  return "Still working through the source.";
}

export function getLifecycleStepIndex(state: BriefingSessionState | null, phase: string): number {
  if (phase === "loading_session" || !state) {
    return 0;
  }
  if (phase === "delivering") {
    return LIFECYCLE_STEPS.length - 1;
  }
  return Math.max(0, LIFECYCLE_STEPS.findIndex((step) => step.states.includes(state)));
}

export function getLifecycleStepDescription({
  activeIndex,
  index,
  phase,
  state,
  step
}: {
  activeIndex: number;
  index: number;
  phase: string;
  state: BriefingSessionState | null;
  step: LifecycleStep;
}): string {
  if (index < activeIndex) return step.completeText;
  if (index > activeIndex) return step.beforeText;
  if (phase === "loading_session") return "Opening the reader.";
  if (phase === "delivering") return "Ready in a moment.";
  if (state === "accepted") return "Warming up.";
  if (state === "resolving_source") return "Finding the signal.";
  if (state === "reusing_existing") return "Checking memory.";
  return step.activeText;
}
