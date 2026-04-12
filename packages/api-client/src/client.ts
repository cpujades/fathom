import createClient from "openapi-fetch";

import type { paths } from "./schema";

type EnvVars = Record<string, string | undefined>;

declare const process: { env?: EnvVars } | undefined;

const getRequiredPublicEnv = (name: string): string => {
  const value = typeof process !== "undefined" ? process.env?.[name]?.trim() : undefined;
  if (!value) {
    throw new Error(
      `Missing ${name}. Set it in apps/web/.env.local for local development and in your deployment environment for production.`
    );
  }

  return value.replace(/\/+$/, "");
};

const getApiBaseUrl = (): string => {
  return getRequiredPublicEnv("NEXT_PUBLIC_API_BASE_URL");
};

const createApiClient = (accessToken?: string) => {
  const baseUrl = getApiBaseUrl();

  return createClient<paths>({
    baseUrl,
    fetch: (input: Request) => {
      const headers = new Headers(input.headers);
      if (accessToken) {
        headers.set("Authorization", `Bearer ${accessToken}`);
      }
      const request = new Request(input, { headers });

      return fetch(request);
    }
  });
};

export { createApiClient, getApiBaseUrl };
