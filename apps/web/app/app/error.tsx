"use client";

import { RouteRecovery } from "../components/RouteRecovery";

export default function AppRouteError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteRecovery
      title="This part of your workspace could not open"
      description="Your saved briefings are still there. Try loading this page again, or return to the workspace."
      error={error}
      homeHref="/app"
      homeLabel="Return to workspace"
      reset={reset}
      scope="app"
    />
  );
}
