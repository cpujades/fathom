import type { PlanResponse } from "@fathom/api-client";

const PLAN_CODE_PATTERN = /^[a-z0-9]+(?:[_-][a-z0-9]+)*$/;
const MAX_PLAN_CODE_LENGTH = 64;

const normalizePlanCode = (value: string): string => {
  return value.trim().toLowerCase();
};

export const resolveRequestedPlan = (
  plans: PlanResponse[],
  intent: string | null,
  planCode: string | null
): PlanResponse | null => {
  if (intent !== "paid" || !planCode) {
    return null;
  }

  const normalizedCode = normalizePlanCode(planCode);
  if (
    normalizedCode.length > MAX_PLAN_CODE_LENGTH ||
    !PLAN_CODE_PATTERN.test(normalizedCode)
  ) {
    return null;
  }

  return (
    plans.find((plan) => normalizePlanCode(plan.plan_code) === normalizedCode) ?? null
  );
};
