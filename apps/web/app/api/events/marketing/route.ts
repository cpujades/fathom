import { NextResponse } from "next/server";

import { logger } from "@/lib/logger";

const ALLOWED_EVENTS = new Set([
  "hero_primary_cta_clicked",
  "hero_secondary_cta_clicked",
  "pricing_mode_toggled",
  "pricing_plan_cta_clicked"
]);

const shouldLogMarketingEvents = process.env.NODE_ENV !== "development";

const isMode = (value: unknown): value is "subscriptions" | "packs" => {
  return value === "subscriptions" || value === "packs";
};

export async function POST(request: Request) {
  let body: unknown;

  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON payload." }, { status: 400 });
  }

  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "Payload must be an object." }, { status: 400 });
  }

  const candidate = body as Record<string, unknown>;
  const { event, section, cta, mode, plan, path, ts } = candidate;

  if (typeof event !== "string" || !ALLOWED_EVENTS.has(event)) {
    return NextResponse.json({ error: "Invalid event name." }, { status: 400 });
  }

  if (typeof section !== "string" || typeof cta !== "string") {
    return NextResponse.json({ error: "Invalid section or cta value." }, { status: 400 });
  }

  if (mode !== undefined && !isMode(mode)) {
    return NextResponse.json({ error: "Invalid mode value." }, { status: 400 });
  }

  if (plan !== undefined && typeof plan !== "string") {
    return NextResponse.json({ error: "Invalid plan value." }, { status: 400 });
  }

  if (typeof path !== "string" || typeof ts !== "string") {
    return NextResponse.json({ error: "Invalid path or timestamp value." }, { status: 400 });
  }

  if (shouldLogMarketingEvents) {
    logger.info("web.marketing_event.received", {
      event,
      section,
      cta,
      mode: mode ?? null,
      plan: plan ?? null,
      path,
      ts
    });
  }

  return new NextResponse(null, { status: 204 });
}
