"use client";

import { RouteRecovery } from "./components/RouteRecovery";

export default function GlobalError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body>
        <RouteRecovery
          title="Talven could not finish loading"
          description="Your saved briefings are unaffected. Try loading Talven again, or return to the home page."
          error={error}
          homeHref="/"
          homeLabel="Return home"
          reset={reset}
          scope="global"
        />
      </body>
    </html>
  );
}
