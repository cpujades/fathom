export const PASSWORD_REQUIREMENTS_MESSAGE = "Password must be at least 12 characters and include a number.";
export const PASSWORD_RECOVERY_COOKIE_NAME = "talven-password-recovery";
export const PASSWORD_RECOVERY_COOKIE_VALUE = "active";
export const PASSWORD_RECOVERY_COOKIE_MAX_AGE_SECONDS = 10 * 60;

export function getPasswordPolicyError(password: string): string | null {
  return password.length >= 12 && /\d/.test(password) ? null : PASSWORD_REQUIREMENTS_MESSAGE;
}

export function validateRecoveryPassword(password: string, confirmation: string): string | null {
  const policyError = getPasswordPolicyError(password);
  if (policyError) {
    return policyError;
  }
  if (password !== confirmation) {
    return "Passwords do not match.";
  }
  return null;
}

export function getPasswordRecoveryErrorMessage(errorCode: string | null | undefined): string | null {
  if (!errorCode) {
    return null;
  }
  if (errorCode === "invalid_or_expired") {
    return "This password reset link is invalid or has expired. Request a new link from sign in.";
  }
  return "Unable to verify this password reset link. Request a new link from sign in.";
}
