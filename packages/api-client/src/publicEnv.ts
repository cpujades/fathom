type PublicUrlOptions = {
  stripTrailingSlashes?: boolean;
};

const DEFAULT_URL_OPTIONS: PublicUrlOptions = {
  stripTrailingSlashes: true
};

const getRequiredPublicEnv = (name: string, value: string | undefined): string => {
  const trimmed = value?.trim();
  if (!trimmed) {
    throw new Error(
      `Missing ${name}. Set it in apps/web/.env.local for local development and in your deployment environment for production.`
    );
  }

  return trimmed;
};

const normalizePublicUrl = (name: string, value: string, options?: PublicUrlOptions): string => {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`Invalid ${name}. Use an absolute URL, for example https://example.com.`);
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`Invalid ${name}. URL must use http or https.`);
  }

  const normalized = parsed.toString();
  if (options?.stripTrailingSlashes ?? DEFAULT_URL_OPTIONS.stripTrailingSlashes) {
    return normalized.replace(/\/+$/, "");
  }

  return normalized;
};

const getRequiredPublicUrlEnv = (name: string, value: string | undefined, options?: PublicUrlOptions): string => {
  const requiredValue = getRequiredPublicEnv(name, value);
  return normalizePublicUrl(name, requiredValue, options);
};

const getOptionalPublicUrlEnv = (name: string, value: string | undefined, options?: PublicUrlOptions): string | null => {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }

  return normalizePublicUrl(name, trimmed, options);
};

export { getOptionalPublicUrlEnv, getRequiredPublicEnv, getRequiredPublicUrlEnv };
