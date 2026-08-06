import { resolveAuthPlanSummary } from "../content/pricing";
import styles from "./auth.module.css";

type AuthPlanSummaryProps = {
  intent: string | null;
  plan: string | null;
};

export function AuthPlanSummary({ intent, plan }: AuthPlanSummaryProps) {
  const selection = resolveAuthPlanSummary(intent, plan);
  if (!selection) {
    return null;
  }

  return (
    <section className={styles.planSummary} aria-labelledby="auth-plan-summary-title">
      <h3 className={styles.planSummaryTitle} id="auth-plan-summary-title">
        Continue with {selection.productName}
      </h3>
      <p className={styles.planSummaryDetails}>
        {selection.price} {selection.paymentCadence} · {selection.includedTime}
      </p>
      <p className={styles.planSummaryNote}>
        Payment has not started. You will review the details before checkout.
      </p>
    </section>
  );
}
