import createClient from "openapi-fetch";

import type { paths } from "./schema";
import { getRequiredPublicUrlEnv } from "./publicEnv";

declare const process:
  | {
      env?: {
        NEXT_PUBLIC_API_BASE_URL?: string;
      };
    }
  | undefined;

const getApiBaseUrl = (): string => {
  return getRequiredPublicUrlEnv(
    "NEXT_PUBLIC_API_BASE_URL",
    typeof process !== "undefined" ? process.env?.NEXT_PUBLIC_API_BASE_URL : undefined
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
