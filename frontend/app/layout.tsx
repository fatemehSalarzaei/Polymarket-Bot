import type { Metadata } from "next";
import Link from "next/link";
import { Toaster } from "sonner";

import { AuthGate } from "@/components/auth/auth-gate";
import { LogoutButton } from "@/components/auth/logout-button";
import "./globals.css";

export const metadata: Metadata = {
  title: "Polymarket BTC Bot",
  description: "Monitoring and paper trading dashboard for BTC Up/Down 15m markets",
};

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/markets/current", label: "Market" },
  { href: "/strategy", label: "Strategy" },
  { href: "/trading", label: "Trading" },
  { href: "/wallet", label: "Wallet" },
  { href: "/orders", label: "Orders" },
  { href: "/pnl", label: "PnL" },
  { href: "/logs", label: "Logs" },
  { href: "/admin", label: "Admin" },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthGate>
        <div className="min-h-screen">
          <aside className="fixed inset-y-0 left-0 hidden w-56 border-r border-zinc-200 bg-white px-4 py-5 md:block">
            <div className="mb-8">
              <p className="text-sm font-semibold text-accent">BTC Up/Down</p>
              <h1 className="text-xl font-bold">Paper Bot</h1>
            </div>
            <nav className="space-y-1">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="block rounded-md px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <LogoutButton />
          </aside>
          <main className="md:pl-56">{children}</main>
        </div>
        </AuthGate>
        <Toaster richColors closeButton />
      </body>
    </html>
  );
}
