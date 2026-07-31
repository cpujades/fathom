"use client";

import { RouteRecovery } from "./components/RouteRecovery";

export default function RouteError({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteRecovery
      title="This page could not open"
      description="Your saved work is unaffected. Try loading the page again, or return to the Talven home page."
      error={error}
      homeHref="/"
      homeLabel="Return home"
      reset={reset}
      scope="route"
    />
  );
}
