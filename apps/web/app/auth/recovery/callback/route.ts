import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import {
  PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS,
  PASSWORD_RECOVERY_COOKIE_NAME,
  PASSWORD_RECOVERY_COOKIE_VALUE
} from "../../../lib/authPolicy";
import { createMiddlewareSupabaseClient } from "../../../lib/supabaseServer";
import { getSafeNextPath, getSiteUrl } from "../../../lib/url";

function buildRecoveryUrl(request: NextRequest, nextPath: string, errorCode?: string): URL {
  let recoveryUrl: URL;
  try {
    recoveryUrl = new URL("/auth/recovery", getSiteUrl());
  } catch {
    recoveryUrl = new URL("/auth/recovery", request.url);
  }
  if (nextPath !== "/app") {
    recoveryUrl.searchParams.set("next", nextPath);
  }
  if (errorCode) {
    recoveryUrl.searchParams.set("recovery_error", errorCode);
  }
  return recoveryUrl;
}

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const nextPath = getSafeNextPath(requestUrl.searchParams.get("next"));
  const code = requestUrl.searchParams.get("code");
  const tokenHash = requestUrl.searchParams.get("token_hash");
  const type = requestUrl.searchParams.get("type");
  const providerError = requestUrl.searchParams.get("error");

  if (providerError) {
    return NextResponse.redirect(buildRecoveryUrl(request, nextPath, "invalid_or_expired"));
  }

  const recoveryUrl = buildRecoveryUrl(request, nextPath);
  const response = NextResponse.redirect(recoveryUrl);
  const supabase = createMiddlewareSupabaseClient(request, response);

  if (tokenHash || type) {
    if (!tokenHash || type !== "recovery") {
      return NextResponse.redirect(buildRecoveryUrl(request, nextPath, "invalid_or_expired"));
    }
    const { error } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type: "recovery"
    });
    if (error) {
      return NextResponse.redirect(buildRecoveryUrl(request, nextPath, "invalid_or_expired"));
    }
  } else if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (error) {
      return NextResponse.redirect(buildRecoveryUrl(request, nextPath, "invalid_or_expired"));
    }
  } else {
    return NextResponse.redirect(buildRecoveryUrl(request, nextPath, "invalid_or_expired"));
  }

  response.cookies.set(PASSWORD_RECOVERY_COOKIE_NAME, PASSWORD_RECOVERY_COOKIE_VALUE, {
    httpOnly: true,
    maxAge: PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS,
    path: "/auth/recovery",
    sameSite: "lax",
    secure: recoveryUrl.protocol === "https:"
  });
  return response;
}
