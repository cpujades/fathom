import { getRequiredPublicEnv, getRequiredPublicUrlEnv } from "@fathom/api-client/publicEnv";

const missingEnvMessage =
  "Missing Supabase public env vars. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY in apps/web/.env.local for local development and in your deployment environment for production.";

export const getSupabasePublicEnv = (): { supabaseUrl: string; supabasePublishableKey: string } => {
  let supabaseUrl: string;
  let supabasePublishableKey: string;
  try {
    supabaseUrl = getRequiredPublicUrlEnv("NEXT_PUBLIC_SUPABASE_URL", process.env.NEXT_PUBLIC_SUPABASE_URL);
    supabasePublishableKey = getRequiredPublicEnv(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
      process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
    );
  } catch {
    throw new Error(missingEnvMessage);
  }

  return { supabaseUrl, supabasePublishableKey };
};
