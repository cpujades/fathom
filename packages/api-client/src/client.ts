import createClient from "openapi-fetch";

import type { paths } from "./schema";

declare const process:
  | {
      env?: {
        NEXT_PUBLIC_API_BASE_URL?: string;
      };
    }
  | undefined;

const getRequiredPublicEnv = (value: string | undefined, name: string): string => {
  const trimmed = value?.trim();
  if (!trimmed) {
    throw new Error(
      `Missing ${name}. Set it in apps/web/.env.local for local development and in your deployment environment for production.`
    );
  }

  return trimmed.replace(/\/+$/, "");
};

const getApiBaseUrl = (): string => {
  return getRequiredPublicEnv(
    typeof process !== "undefined" ? process.env?.NEXT_PUBLIC_API_BASE_URL : undefined,
    "NEXT_PUBLIC_API_BASE_URL"
  );
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
