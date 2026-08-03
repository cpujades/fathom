const getConfiguredOrigin = (name, value) => {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }

  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error(`Invalid ${name}. Use an absolute http(s) URL.`);
  }

  if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error(`Invalid ${name}. Use an absolute http(s) URL without credentials.`);
  }
  return parsed.origin;
};

const isLoopbackOrigin = (origin) => {
  const hostname = new URL(origin).hostname;
  return hostname === "localhost" || hostname.endsWith(".localhost");
};

const requireProductionHttps = (name, origin, env) => {
  if (
    env.NODE_ENV === "production" &&
    origin &&
    !origin.startsWith("https://") &&
    !isLoopbackOrigin(origin)
  ) {
    throw new Error(`Invalid ${name}. Hosted production origins must use https.`);
  }
};

const buildContentSecurityPolicy = (env = process.env) => {
  const apiOrigin = getConfiguredOrigin(
    "NEXT_PUBLIC_API_BASE_URL",
    env.NEXT_PUBLIC_API_BASE_URL
  );
  const supabaseOrigin = getConfiguredOrigin(
    "NEXT_PUBLIC_SUPABASE_URL",
    env.NEXT_PUBLIC_SUPABASE_URL
  );
  const siteOrigin = getConfiguredOrigin(
    "NEXT_PUBLIC_SITE_URL",
    env.NEXT_PUBLIC_SITE_URL
  );
  requireProductionHttps("NEXT_PUBLIC_API_BASE_URL", apiOrigin, env);
  requireProductionHttps("NEXT_PUBLIC_SUPABASE_URL", supabaseOrigin, env);
  requireProductionHttps("NEXT_PUBLIC_SITE_URL", siteOrigin, env);
  if (env.NODE_ENV === "production" && !siteOrigin) {
    throw new Error(
      "Missing NEXT_PUBLIC_SITE_URL. Set the exact public frontend origin for a hosted build."
    );
  }
  const connectSources = [
    "'self'",
    ...new Set([apiOrigin, supabaseOrigin].filter(Boolean))
  ];
  const scriptSources = ["'self'", "'unsafe-inline'"];
  if (env.NODE_ENV !== "production") {
    scriptSources.push("'unsafe-eval'");
  }

  const directives = [
    "default-src 'self'",
    "base-uri 'self'",
    `connect-src ${connectSources.join(" ")}`,
    "font-src 'self' data:",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "frame-src 'none'",
    "img-src 'self' data: blob: https://i.ytimg.com",
    "media-src 'self'",
    "object-src 'none'",
    `script-src ${scriptSources.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "worker-src 'self' blob:"
  ];

  if (
    env.NODE_ENV === "production" &&
    siteOrigin?.startsWith("https://") &&
    [apiOrigin, supabaseOrigin].every(
      (origin) => !origin || origin.startsWith("https://")
    )
  ) {
    directives.push("upgrade-insecure-requests");
  }

  return directives.join("; ");
};

const buildSecurityHeaders = (env = process.env) => {
  const headers = [
    {
      key: "Content-Security-Policy",
      value: buildContentSecurityPolicy(env)
    },
    {
      key: "Permissions-Policy",
      value: "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    },
    {
      key: "Referrer-Policy",
      value: "strict-origin-when-cross-origin"
    },
    {
      key: "X-Content-Type-Options",
      value: "nosniff"
    },
    {
      key: "X-Frame-Options",
      value: "DENY"
    }
  ];

  const siteOrigin = getConfiguredOrigin(
    "NEXT_PUBLIC_SITE_URL",
    env.NEXT_PUBLIC_SITE_URL
  );
  if (env.NODE_ENV === "production" && siteOrigin?.startsWith("https://")) {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=31536000; includeSubDomains"
    });
  }

  return headers;
};

export { buildContentSecurityPolicy, buildSecurityHeaders };
