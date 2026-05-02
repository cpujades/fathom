import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getSupabasePublicEnv } from "./supabaseConfig";

let client: SupabaseClient | null = null;

export const getSupabaseClient = (): SupabaseClient => {
  if (client) {
    return client;
  }

  const { supabaseUrl, supabasePublishableKey } = getSupabasePublicEnv();
  client = createBrowserClient(supabaseUrl, supabasePublishableKey);
  return client;
};
