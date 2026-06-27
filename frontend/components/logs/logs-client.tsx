"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getLogs } from "@/lib/api-client";
import type { AuditLog } from "@/types/log";
import { LogsTable } from "@/components/logs/logs-table";

export function LogsClient() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getLogs();
        if (!cancelled) setLogs(data);
      } catch (err) {
        if (!cancelled) toast.error(err instanceof Error ? err.message : "Failed to load logs");
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
        <p className="text-sm font-semibold text-accent">Audit trail</p>
        <h2 className="mt-1 text-3xl font-bold tracking-normal">Logs</h2>
      </div>
      {loading ? <div className="mb-4 rounded-md border border-zinc-200 bg-white p-4 text-sm text-muted">Loading</div> : null}
      <LogsTable logs={logs} />
    </section>
  );
}

