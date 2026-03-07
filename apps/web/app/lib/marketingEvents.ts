"use client";

type MarketingEventName =
  | "hero_primary_cta_clicked"
  | "hero_secondary_cta_clicked"
  | "pricing_mode_toggled"
  | "pricing_plan_cta_clicked";

type MarketingEventPayload = {
  event: MarketingEventName;
  section: string;
  cta: string;
  mode?: "subscriptions" | "packs";
  plan?: string;
};

type MarketingEventEnvelope = MarketingEventPayload & {
  path: string;
  ts: string;
};

const MARKETING_ENDPOINT = "/api/events/marketing";

const sendViaFetch = (payload: MarketingEventEnvelope) => {
  void fetch(MARKETING_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    keepalive: true
  }).catch(() => {
    // Ignore telemetry failures.
  });
};

const trackMarketingEvent = (payload: MarketingEventPayload) => {
  if (typeof window === "undefined") {
    return;
  }

  const envelope: MarketingEventEnvelope = {
    ...payload,
    path: window.location.pathname,
    ts: new Date().toISOString()
  };

  if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    const blob = new Blob([JSON.stringify(envelope)], { type: "application/json" });
    const sent = navigator.sendBeacon(MARKETING_ENDPOINT, blob);
    if (sent) {
      return;
    }
  }

  sendViaFetch(envelope);
};

export type { MarketingEventName, MarketingEventPayload };
export { trackMarketingEvent };
