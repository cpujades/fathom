import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { createMiddlewareSupabaseClient } from "./app/lib/supabaseServer";
import {
  buildAuthDestinationPath,
  getSafeAuthIntentContext,
  getSafeNextPath
} from "./app/lib/url";

const buildSignInRedirect = (request: NextRequest): URL => {
  const redirectUrl = request.nextUrl.clone();
  redirectUrl.pathname = "/signin";
  redirectUrl.search = "";

  const nextPath = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  if (nextPath !== "/app") {
    redirectUrl.searchParams.set("next", nextPath);
  }

  return redirectUrl;
};

const copyResponseCookies = (source: NextResponse, destination: NextResponse): NextResponse => {
  for (const cookie of source.cookies.getAll()) {
    destination.cookies.set(cookie);
  }
  return destination;
};

const buildAuthenticatedDestination = (request: NextRequest): URL => {
  const authIntent = getSafeAuthIntentContext({
    intent: request.nextUrl.searchParams.get("intent"),
    plan: request.nextUrl.searchParams.get("plan")
  });
  const nextPath = getSafeNextPath(request.nextUrl.searchParams.get("next"));
  const destinationPath = buildAuthDestinationPath(nextPath, authIntent);
  return new URL(destinationPath, request.url);
};

export async function proxy(request: NextRequest) {
  const response = NextResponse.next();
  const supabase = createMiddlewareSupabaseClient(request, response);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const isAuthEntry = request.nextUrl.pathname === "/signin" || request.nextUrl.pathname === "/signup";

  if (user && isAuthEntry) {
    return copyResponseCookies(response, NextResponse.redirect(buildAuthenticatedDestination(request)));
  }

  if (!user && !isAuthEntry) {
    return copyResponseCookies(response, NextResponse.redirect(buildSignInRedirect(request)));
  }

  return response;
}

export const config = {
  matcher: ["/app/:path*", "/signin", "/signup"],
};
