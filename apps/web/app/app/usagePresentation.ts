type CreationUsage = {
  debt_seconds: number;
  is_blocked: boolean;
  total_remaining_seconds: number;
};

export type CreationAccessState = {
  canCreate: boolean;
  debtSeconds: number;
  hasNoCredits: boolean;
};

export const getCreationAccessState = (usage: CreationUsage | null): CreationAccessState => {
  return {
    canCreate: usage === null || (usage.is_blocked !== true && usage.total_remaining_seconds > 0),
    debtSeconds: Math.max(usage?.debt_seconds ?? 0, 0),
    hasNoCredits: usage !== null && usage.total_remaining_seconds <= 0
  };
};
