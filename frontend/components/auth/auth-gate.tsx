"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe } from "@/lib/api-client";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(pathname === "/login");

  useEffect(() => {
    setReady(pathname === "/login");
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
