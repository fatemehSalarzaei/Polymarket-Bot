"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { disableTrading, enableTrading, getTradingReadiness } from "@/lib/api-client";
import type { TradingReadiness } from "@/types/trading";

export function TradingClient() {
  const [readiness, setReadiness] = useState<TradingReadiness | null>(null);
  const [phrase, setPhrase] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    const next = await getTradingReadiness();
    setReadiness(next);
  }

  useEffect(() => {
    void load().catch((error) => toast.error(error instanceof Error ? error.message : "Failed to load trading readiness"));
  }, []);

  async function run(action: "enable" | "disable") {
    setLoading(true);
    try {
      if (action === "enable") {
        await enableTrading(phrase);
        setPhrase("");
      } else {
        await disableTrading();
      }
      await load();
      toast.success(action === "enable" ? "Real trading setting enabled" : "Real trading disabled");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Trading action failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="space-y-6 p-6">
      <section>
        <p className="text-sm font-semibold text-accent">User trading controls</p>
        <h1 className="text-2xl font-bold text-ink">Trading</h1>
      </section>
      <section className="grid gap-4 md:grid-cols-3">
        <Metric label="Wallet ready" value={readiness?.wallet.trading_ready ? "yes" : "no"} />
        <Metric label="Geoblock" value={readiness?.geoblock.blocked ? "blocked" : "clear"} />
        <Metric label="Dry-run" value={readiness?.real_order_dry_run ? "enabled" : "disabled"} />
        <Metric label="Paper trading" value={readiness?.paper_trading_enabled ? "enabled" : "disabled"} />
        <Metric label="Real trading" value={readiness?.trading_enabled ? "enabled" : "disabled"} />
        <Metric label="Kill switch" value={readiness?.kill_switch_active ? "active" : "inactive"} />
      </section>
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="font-semibold text-ink">Readiness blockers</h2>
        {readiness?.blocking_reasons.length ? (
          <ul className="mt-3 space-y-2 text-sm text-red-700">
            {readiness.blocking_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-zinc-600">No blockers reported.</p>
        )}
      </section>
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <label className="block text-sm font-medium text-zinc-700">
          Confirmation phrase
          <input className="input mt-1 w-full" value={phrase} onChange={(event) => setPhrase(event.target.value)} placeholder="ENABLE REAL TRADING" />
        </label>
        <div className="mt-4 flex gap-3">
          <button className="btn-danger" disabled={loading || phrase !== "ENABLE REAL TRADING"} onClick={() => void run("enable")}>
            Enable real trading
          </button>
          <button className="btn-secondary" disabled={loading} onClick={() => void run("disable")}>
            Disable real trading
          </button>
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase text-zinc-500">{label}</p>
      <p className="mt-2 text-lg font-bold text-ink">{value}</p>
    </div>
  );
}
