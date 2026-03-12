import type { ReactNode } from "react";

import { AppShellProvider } from "../components/AppShellProvider";

export default function AuthenticatedAppLayout({ children }: { children: ReactNode }) {
  return <AppShellProvider>{children}</AppShellProvider>;
}
