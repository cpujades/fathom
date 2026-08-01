import { NextResponse } from "next/server";

import { PASSWORD_RECOVERY_COOKIE_NAME } from "../../../lib/authPolicy";

export async function POST() {
  const response = NextResponse.json({ status: "ok" });
  response.cookies.set(PASSWORD_RECOVERY_COOKIE_NAME, "", {
    httpOnly: true,
    maxAge: 0,
    path: "/auth/recovery",
    sameSite: "lax"
  });
  return response;
}
