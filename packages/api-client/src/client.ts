import createClient from "openapi-fetch";

import type { paths } from "./schema";

type EnvVars = Record<string, string | undefined>;

declare const process: { env?: EnvVars } | undefined;

const getApiBaseUrl = (): string => {
  const envBaseUrl =
    typeof process !== "undefined" ? process.env?.NEXT_PUBLIC_API_BASE_URL : undefined;

  return envBaseUrl ?? "http://localhost:8080";
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
