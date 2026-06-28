"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe } from "@/lib/api-client";
import type { User } from "@/types/auth";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(pathname === "/login");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (pathname === "/login") {
      setReady(true);
      return;
    }
    let cancelled = false;
    getMe()
      .then((me) => {
        if (cancelled) return;
        if (!me.authenticated || !me.user) {
          router.replace("/login");
          return;
        }
        if (pathname.startsWith("/admin") && me.user.role !== "admin") {
          router.replace("/dashboard");
          return;
        }
        setUser(me.user);
        setReady(true);
      })
      .catch(() => {
        if (!cancelled) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (!ready) {
    return <main className="p-6 text-sm text-zinc-600">Loading session...</main>;
  }
  return <>{children}</>;
}
