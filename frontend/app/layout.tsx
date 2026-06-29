import type { Metadata } from "next";
import { Toaster } from "sonner";

import { AuthGate } from "@/components/auth/auth-gate";
import { AppShell } from "@/components/layout/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polymarket BTC Bot",
  description: "Monitoring and paper trading dashboard for BTC Up/Down 15m markets",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthGate>
          <AppShell>{children}</AppShell>
        </AuthGate>
        <Toaster richColors closeButton />
      </body>
    </html>
  );
}
