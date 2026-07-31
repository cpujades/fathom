import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";

import { createMiddlewareSupabaseClient } from "../../lib/supabaseServer";
import {
  buildAuthDestinationPath,
  buildSignInPath,
  getSafeAuthIntentContext,
  getSafeNextPath,
  getSiteUrl,
  type SafeAuthIntentContext
} from "../../lib/url";

const buildRedirectUrl = (request: NextRequest, path: string): URL => {
  try {
    return new URL(path, getSiteUrl());
  } catch {
    return new URL(path, request.url);
  }
};

const buildAuthErrorRedirect = (
  request: NextRequest,
  nextPath: string,
  authIntent: SafeAuthIntentContext,
  authErrorCode: string
): NextResponse => {
  const redirectUrl = buildRedirectUrl(request, buildSignInPath(nextPath, authIntent));
  redirectUrl.searchParams.set("auth_error", authErrorCode);
  return NextResponse.redirect(redirectUrl);
};

const isEmailOtpType = (candidate: string | null): candidate is EmailOtpType => {
  return (
    candidate === "signup" ||
    candidate === "invite" ||
    candidate === "magiclink" ||
    candidate === "recovery" ||
    candidate === "email_change" ||
    candidate === "email"
  );
};

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const tokenHash = requestUrl.searchParams.get("token_hash");
  const type = requestUrl.searchParams.get("type");
  const error = requestUrl.searchParams.get("error");
  const nextPath = getSafeNextPath(requestUrl.searchParams.get("next"));
  const authIntent = getSafeAuthIntentContext({
    intent: requestUrl.searchParams.get("intent"),
    plan: requestUrl.searchParams.get("plan")
  });

  if (error) {
    return buildAuthErrorRedirect(request, nextPath, authIntent, "authentication_failed");
  }

  const destinationPath = buildAuthDestinationPath(nextPath, authIntent);
  const redirectUrl = buildRedirectUrl(request, destinationPath);
  const response = NextResponse.redirect(redirectUrl);
  const supabase = createMiddlewareSupabaseClient(request, response);

  if (tokenHash || type) {
    if (!tokenHash || !isEmailOtpType(type)) {
      return buildAuthErrorRedirect(request, nextPath, authIntent, "invalid_email_link");
    }

    const { error: verifyError } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type,
    });

    if (verifyError) {
      return buildAuthErrorRedirect(request, nextPath, authIntent, "verify_link_failed");
    }

    return response;
  }

  if (!code) {
    return buildAuthErrorRedirect(request, nextPath, authIntent, "missing_auth_code");
  }

  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);

  if (exchangeError) {
    return buildAuthErrorRedirect(request, nextPath, authIntent, "session_exchange_failed");
  }

  return response;
}
