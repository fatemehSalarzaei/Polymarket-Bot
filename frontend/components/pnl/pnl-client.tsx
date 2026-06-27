"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getPnlSummary } from "@/lib/api-client";
import type { PnlSummary } from "@/types/pnl";
import { PnlCards } from "@/components/dashboard/pnl-card";

export function PnlClient() {
  const [summary, setSummary] = useState<PnlSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getPnlSummary();
        if (!cancelled) setSummary(data);
      } catch (err) {
        if (!cancelled) toast.error(err instanceof Error ? err.message : "Failed to load PnL summary");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-6">
        <p className="text-sm font-semibold text-accent">Paper and real trading summary</p>
        <h2 className="mt-1 text-3xl font-bold tracking-normal">PnL</h2>
      </div>
      {loading ? <div className="mb-4 rounded-md border border-zinc-200 bg-white p-4 text-sm text-muted">Loading</div> : null}
      <PnlCards summary={summary} />
    </section>
  );
}

