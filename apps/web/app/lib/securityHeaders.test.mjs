import assert from "node:assert/strict";
import test from "node:test";

import {
  buildContentSecurityPolicy,
  buildSecurityHeaders
} from "./securityHeaders.mjs";

const productionEnv = {
  NODE_ENV: "production",
  NEXT_PUBLIC_API_BASE_URL: "https://api.talven.ai/v1",
  NEXT_PUBLIC_SITE_URL: "https://app.talven.ai",
  NEXT_PUBLIC_SUPABASE_URL: "https://project.supabase.co"
};

test("production CSP allows only configured service origins", () => {
  const policy = buildContentSecurityPolicy(productionEnv);

  assert.match(
    policy,
    /connect-src 'self' https:\/\/api\.talven\.ai https:\/\/project\.supabase\.co/
  );
  assert.match(policy, /frame-ancestors 'none'/);
  assert.match(policy, /object-src 'none'/);
  assert.match(policy, /upgrade-insecure-requests/);
  assert.doesNotMatch(policy, /unsafe-eval/);
  assert.doesNotMatch(policy, /connect-src[^;]*\*/);
});

test("development CSP permits Next development evaluation without broad network wildcards", () => {
  const policy = buildContentSecurityPolicy({
    NODE_ENV: "development",
    NEXT_PUBLIC_API_BASE_URL: "http://localhost:8080",
    NEXT_PUBLIC_SUPABASE_URL: "http://localhost:54321"
  });

  assert.match(policy, /script-src 'self' 'unsafe-inline' 'unsafe-eval'/);
  assert.match(
    policy,
    /connect-src 'self' http:\/\/localhost:8080 http:\/\/localhost:54321/
  );
  assert.doesNotMatch(policy, /upgrade-insecure-requests/);
});

test("production headers include clickjacking, MIME, referrer, permissions, and HSTS controls", () => {
  const headers = new Map(
    buildSecurityHeaders(productionEnv).map(({ key, value }) => [key, value])
  );

  assert.equal(headers.get("X-Frame-Options"), "DENY");
  assert.equal(headers.get("X-Content-Type-Options"), "nosniff");
  assert.equal(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin");
  assert.match(headers.get("Permissions-Policy"), /camera=\(\)/);
  assert.equal(
    headers.get("Strict-Transport-Security"),
    "max-age=31536000; includeSubDomains"
  );
});

test("invalid configured public URLs fail the build instead of widening CSP", () => {
  assert.throws(
    () =>
      buildContentSecurityPolicy({
        NODE_ENV: "production",
        NEXT_PUBLIC_API_BASE_URL: "javascript:alert(1)"
      }),
    /Invalid NEXT_PUBLIC_API_BASE_URL/
  );
  assert.throws(
    () =>
      buildContentSecurityPolicy({
        NODE_ENV: "production",
        NEXT_PUBLIC_SUPABASE_URL: "https://user:pass@project.supabase.co"
      }),
    /without credentials/
  );
});

test("a production build requires an explicit canonical site origin", () => {
  assert.throws(
    () =>
      buildSecurityHeaders({
        NODE_ENV: "production",
        NEXT_PUBLIC_API_BASE_URL: "https://api.talven.ai",
        NEXT_PUBLIC_SUPABASE_URL: "https://project.supabase.co"
      }),
    /Missing NEXT_PUBLIC_SITE_URL/
  );
});

test("hosted production origins must use HTTPS", () => {
  assert.throws(
    () =>
      buildSecurityHeaders({
        NODE_ENV: "production",
        NEXT_PUBLIC_API_BASE_URL: "http://api.talven.ai",
        NEXT_PUBLIC_SITE_URL: "https://app.talven.ai",
        NEXT_PUBLIC_SUPABASE_URL: "https://project.supabase.co"
      }),
    /NEXT_PUBLIC_API_BASE_URL.*https/
  );
});
