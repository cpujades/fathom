export const buildPaidCheckoutHref = (planCode: string): string => {
  const params = new URLSearchParams({
    next: "/app/billing",
    intent: "paid",
    plan: planCode
  });

  return `/signup?${params.toString()}`;
};
