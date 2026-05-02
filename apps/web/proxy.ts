import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { createMiddlewareSupabaseClient } from "./app/lib/supabaseServer";

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

export async function proxy(request: NextRequest) {
  const response = NextResponse.next();
  const supabase = createMiddlewareSupabaseClient(request, response);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.redirect(buildSignInRedirect(request));
  }

  return response;
}

export const config = {
  matcher: ["/app/:path*"],
};
