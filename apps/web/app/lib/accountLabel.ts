import type { User } from "@supabase/supabase-js";

export const getAccountLabel = (user: Pick<User, "email" | "user_metadata"> | null): string | null => {
  if (!user) {
    return null;
  }

  const fullName =
    (user.user_metadata?.full_name as string | undefined) ?? (user.user_metadata?.name as string | undefined);
  if (fullName && fullName.trim().length > 0) {
    return fullName.trim();
  }

  const email = user.email ?? null;
  if (!email) {
    return null;
  }

  const localPart = email.split("@")[0];
  return localPart || email;
};
