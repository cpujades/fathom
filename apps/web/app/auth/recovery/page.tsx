import { cookies } from "next/headers";

import {
  PASSWORD_RECOVERY_COOKIE_NAME,
  PASSWORD_RECOVERY_COOKIE_VALUE
} from "../../lib/authPolicy";
import { getSafeNextPath } from "../../lib/url";
import styles from "../auth.module.css";
import { PasswordRecoveryForm } from "./PasswordRecoveryForm";

type PasswordRecoveryPageProps = {
  searchParams: Promise<{
    next?: string | string[];
    recovery_error?: string | string[];
  }>;
};

function firstValue(value: string | string[] | undefined): string | null {
  return Array.isArray(value) ? value[0] ?? null : value ?? null;
}

export default async function PasswordRecoveryPage({ searchParams }: PasswordRecoveryPageProps) {
  const [params, cookieStore] = await Promise.all([searchParams, cookies()]);
  const nextPath = getSafeNextPath(firstValue(params.next));
  const errorCode = firstValue(params.recovery_error);
  const recoveryReady =
    !errorCode && cookieStore.get(PASSWORD_RECOVERY_COOKIE_NAME)?.value === PASSWORD_RECOVERY_COOKIE_VALUE;

  return (
    <div className={styles.page}>
      <main className={styles.shell} id="main-content">
        <aside className={styles.panel}>
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true" />
            Talven
          </div>
          <h1 className={styles.panelTitle}>Secure your account</h1>
          <p className={styles.panelText}>Finish the reset before returning to your private briefings.</p>
          <ul className={styles.panelList}>
            <li>Use a unique password</li>
            <li>Keep reset links private</li>
            <li>Expired links can be requested again safely</li>
          </ul>
        </aside>

        <PasswordRecoveryForm errorCode={errorCode} nextPath={nextPath} recoveryReady={recoveryReady} />
      </main>
    </div>
  );
}
