"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LogoutButton } from "@/components/auth/logout-button";

const navItems = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/markets/current", label: "Market" },
  { href: "/strategy", label: "Strategy" },
  { href: "/trading", label: "Trading" },
  { href: "/wallet", label: "Wallet" },
  { href: "/orders", label: "Orders" },
  { href: "/pnl", label: "PnL" },
  { href: "/logs", label: "Logs" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return <>{children}</>;
  }

  return (
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
  );
}
