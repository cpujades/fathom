type AuthErrorShape = {
  message?: string | null;
  status?: number | null;
  code?: string | null;
  name?: string | null;
};

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  email_exists: "An account with this email already exists. Try signing in instead.",
  user_already_exists: "An account with this email already exists. Try signing in instead.",
  email_not_confirmed: "Please confirm your email before signing in.",
  user_not_found: "No account found for this email. Please sign up first.",
  invalid_credentials: "No account found or incorrect password.",
  weak_password: "Password is too weak. Use at least 12 characters and include a number.",
  email_address_invalid: "Enter a valid email address.",
  validation_failed: "Check your details and try again.",
  signup_disabled: "Sign-ups are currently disabled.",
  otp_disabled: "Magic link sign-in is currently disabled.",
  provider_disabled: "This login provider is currently disabled.",
  email_provider_disabled: "Email sign-in is currently disabled.",
  oauth_provider_not_supported: "This login provider is not supported.",
  email_address_not_authorized: "Email delivery is restricted for this address.",
  over_email_send_rate_limit: "Too many emails sent. Please wait and try again.",
  over_request_rate_limit: "Too many requests. Please wait and try again.",
  user_banned: "This account has been disabled. Contact support."
};

const mapAuthError = (error: AuthErrorShape | null, fallback: string): string => {
  if (!error) {
    return fallback;
  }

  const code = error.code?.toLowerCase();
  if (code && AUTH_ERROR_MESSAGES[code]) {
    return AUTH_ERROR_MESSAGES[code];
  }

  if (error.status === 429) {
    return "Too many requests. Please wait and try again.";
  }

  if (error.message) {
    return error.message;
  }

  return fallback;
};

export { mapAuthError };
export type { AuthErrorShape };
