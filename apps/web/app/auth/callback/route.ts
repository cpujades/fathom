import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";

import { createMiddlewareSupabaseClient } from "../../lib/supabaseServer";
import { buildSignInPath, getSafeNextPath, getSiteUrl } from "../../lib/url";

const buildRedirectUrl = (request: NextRequest, path: string): URL => {
  return new URL(path, getSiteUrl() || request.url);
};

const buildAuthErrorRedirect = (request: NextRequest, nextPath: string, message: string): NextResponse => {
  const redirectUrl = buildRedirectUrl(request, buildSignInPath(nextPath));
  redirectUrl.searchParams.set("auth_error", message);
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
  const errorDescription = requestUrl.searchParams.get("error_description");
  const nextPath = getSafeNextPath(requestUrl.searchParams.get("next"));

  if (error) {
    return buildAuthErrorRedirect(request, nextPath, errorDescription || "Authentication failed.");
  }

  const redirectUrl = buildRedirectUrl(request, nextPath);
  const response = NextResponse.redirect(redirectUrl);
  const supabase = createMiddlewareSupabaseClient(request, response);

  if (tokenHash || type) {
    if (!tokenHash || !isEmailOtpType(type)) {
      return buildAuthErrorRedirect(request, nextPath, "The email sign-in link is invalid. Please request a new one.");
    }

    const { error: verifyError } = await supabase.auth.verifyOtp({
      token_hash: tokenHash,
      type,
    });

    if (verifyError) {
      return buildAuthErrorRedirect(request, nextPath, verifyError.message);
    }

    return response;
  }

  if (!code) {
    return buildAuthErrorRedirect(request, nextPath, "No authentication code was returned. Please sign in again.");
  }

  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);

  if (exchangeError) {
    return buildAuthErrorRedirect(request, nextPath, exchangeError.message);
  }

  return response;
}
