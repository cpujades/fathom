const missingEnvMessage =
  "Missing Supabase public env vars. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY in apps/web/.env.local for local development and in your deployment environment for production.";

export const getSupabasePublicEnv = (): { supabaseUrl: string; supabasePublishableKey: string } => {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const supabasePublishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();

  if (!supabaseUrl || !supabasePublishableKey) {
    throw new Error(missingEnvMessage);
  }

  return { supabaseUrl, supabasePublishableKey };
};
