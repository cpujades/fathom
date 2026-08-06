const SIGN_IN_EMAIL_TRANSFER_KEY = "talven:auth:sign-in-email";

const storeSignInEmail = (storage: Storage, email: string): void => {
  const normalizedEmail = email.trim();
  if (!normalizedEmail) {
    storage.removeItem(SIGN_IN_EMAIL_TRANSFER_KEY);
    return;
  }

  storage.setItem(SIGN_IN_EMAIL_TRANSFER_KEY, normalizedEmail);
};

const takeSignInEmail = (storage: Storage): string | null => {
  const email = storage.getItem(SIGN_IN_EMAIL_TRANSFER_KEY)?.trim() ?? "";
  storage.removeItem(SIGN_IN_EMAIL_TRANSFER_KEY);
  return email || null;
};

export { SIGN_IN_EMAIL_TRANSFER_KEY, storeSignInEmail, takeSignInEmail };
