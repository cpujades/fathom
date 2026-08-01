export type AuthenticatedRequestScope = Readonly<{
  generation: number;
  userId: string;
}>;

export class AuthenticatedDataScopeChangedError extends Error {
  constructor() {
    super("Authenticated data scope changed while the request was in flight.");
    this.name = "AuthenticatedDataScopeChangedError";
  }
}

function normalizeUserId(userId: string | null): string | null {
  const normalized = userId?.trim() ?? "";
  return normalized || null;
}

export class AuthenticatedDataScopeController {
  #activeUserId: string | null = null;
  #generation = 0;

  reset(userId: string | null): { nextUserId: string | null; previousUserId: string | null } {
    const previousUserId = this.#activeUserId;
    const nextUserId = normalizeUserId(userId);
    this.#activeUserId = nextUserId;
    this.#generation += 1;
    return { nextUserId, previousUserId };
  }

  capture(userId: string): AuthenticatedRequestScope {
    const normalizedUserId = normalizeUserId(userId);
    if (!normalizedUserId || normalizedUserId !== this.#activeUserId) {
      throw new AuthenticatedDataScopeChangedError();
    }
    return Object.freeze({ generation: this.#generation, userId: normalizedUserId });
  }

  isCurrent(scope: AuthenticatedRequestScope): boolean {
    return scope.userId === this.#activeUserId && scope.generation === this.#generation;
  }

  assertCurrent(scope: AuthenticatedRequestScope): void {
    if (!this.isCurrent(scope)) {
      throw new AuthenticatedDataScopeChangedError();
    }
  }
}
