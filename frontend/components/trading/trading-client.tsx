"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { disableTrading, enableTrading, getTradingReadiness } from "@/lib/api-client";
import { readinessMessage } from "@/lib/readiness-messages";
import type { TradingReadiness } from "@/types/trading";

export function TradingClient() {
  const [readiness, setReadiness] = useState<TradingReadiness | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
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
        await enableTrading();
        setConfirmOpen(false);
      } else {
        await disableTrading();
      }
      await load();
      toast.success(action === "enable" ? `${modeLabel(readiness)} trading setting enabled` : "Trading disabled");
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
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="font-semibold text-ink">Current Mode</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <Metric label="Paper trading" value={readiness?.paper_trading_ready ? "ready" : "not ready"} />
          <Metric label="Dry-run trading" value={readiness?.dry_run_trading_ready ? "ready" : "not ready"} />
          <Metric label="Real trading availability" value={readiness?.real_trading_available ? "available" : "unavailable"} />
          <Metric label="Execution setting" value={readiness?.trading_enabled ? "enabled" : "disabled"} />
          <Metric label="Kill switch" value={readiness?.kill_switch_active ? "active" : "inactive"} />
          <Metric label="Geoblock" value={!readiness?.geoblock.checked ? "unchecked" : readiness.geoblock.blocked ? "blocked" : "clear"} />
        </div>
      </section>
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="font-semibold text-ink">Warnings</h2>
        {readiness?.warnings.length ? (
          <ul className="mt-3 space-y-3 text-sm">
            {readiness.warnings.map((reason) => (
              <ReadinessItem key={reason} code={reason} tone="warning" />
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-zinc-600">No warnings reported.</p>
        )}
      </section>
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="font-semibold text-ink">Blockers</h2>
        {readiness?.blocking_reasons.length ? (
          <ul className="mt-3 space-y-3 text-sm">
            {readiness.blocking_reasons.map((reason) => (
              <ReadinessItem key={reason} code={reason} tone="blocker" />
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-zinc-600">No blockers reported.</p>
        )}
      </section>
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="font-semibold text-ink">Activation</h2>
        <p className="mt-2 text-sm text-zinc-600">
          {readiness?.real_order_dry_run
            ? "Dry-run trading enables execution while the backend simulates real orders."
            : "Real trading allows the bot to submit real Polymarket orders using your configured wallet."}
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button className="btn-danger" disabled={enableDisabled(readiness, loading)} onClick={() => setConfirmOpen(true)}>
            {readiness?.real_order_dry_run ? "Enable dry-run trading" : "Enable real trading"}
          </button>
          <button className="btn-secondary" disabled={loading} onClick={() => void run("disable")}>
            Disable trading
          </button>
        </div>
        {enableDisabled(readiness, loading) ? <p className="mt-3 text-sm text-zinc-600">{disabledReason(readiness, loading)}</p> : null}
      </section>
      {confirmOpen ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-md bg-white p-5 shadow-xl">
            <h2 className="text-lg font-semibold text-ink">
              {readiness?.real_order_dry_run ? "Enable dry-run trading?" : "Enable real trading?"}
            </h2>
            <p className="mt-3 text-sm text-zinc-700">
              {readiness?.real_order_dry_run
                ? "This enables trading execution while backend dry-run mode is active. Orders will be simulated."
                : "Are you sure you want to enable real trading? The bot may submit real orders using your configured wallet."}
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button className="btn-secondary" disabled={loading} onClick={() => setConfirmOpen(false)}>
                Cancel
              </button>
              <button className="btn-danger" disabled={loading} onClick={() => void run("enable")}>
                {readiness?.real_order_dry_run ? "Yes, enable dry-run trading" : "Yes, enable real trading"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function enableDisabled(readiness: TradingReadiness | null, loading: boolean) {
  if (loading || readiness === null || readiness.trading_enabled || readiness.kill_switch_active || readiness.wallet.trading_ready !== true) {
    return true;
  }
  if (readiness.real_order_dry_run) {
    return readiness.dry_run_trading_ready !== true || readiness.trading_ready !== true;
  }
  return (
    readiness.trading_ready !== true ||
    readiness.real_trading_available !== true ||
    readiness.real_trading_ready !== true
  );
}

function disabledReason(readiness: TradingReadiness | null, loading: boolean) {
  if (loading || readiness === null) {
    return "Checking trading readiness...";
  }
  if (readiness.trading_enabled) {
    return `${modeLabel(readiness)} trading is already enabled.`;
  }
  if (readiness.kill_switch_active) {
    return "Disable the kill switch before enabling trading execution.";
  }
  if (!readiness.wallet.trading_ready) {
    return "Wallet setup is not ready for trading execution.";
  }
  if (readiness.real_order_dry_run && !readiness.dry_run_trading_ready) {
    return "Resolve the readiness blockers before enabling dry-run trading.";
  }
  if (!readiness.real_order_dry_run && !readiness.real_trading_available) {
    return "Real trading is unavailable until all real-money safety checks pass.";
  }
  if (!readiness.trading_ready) {
    return "Resolve the readiness blockers before enabling real trading.";
  }
  return "";
}

function modeLabel(readiness: TradingReadiness | null) {
  return readiness?.real_order_dry_run ? "Dry-run" : "Real";
}

function ReadinessItem({ code, tone }: { code: string; tone: "warning" | "blocker" }) {
  const copy = readinessMessage(code);
  const classes =
    tone === "warning"
      ? "border-amber-100 bg-amber-50 text-amber-950"
      : "border-red-100 bg-red-50 text-red-900";
  const bodyClass = tone === "warning" ? "text-amber-900" : "text-red-800";
  const codeClass = tone === "warning" ? "text-amber-800" : "text-red-700";
  return (
    <li className={`rounded-md border p-3 ${classes}`}>
      <p className="font-semibold">{copy.title}</p>
      <p className={`mt-1 ${bodyClass}`}>{copy.message}</p>
      {copy.action ? <p className={`mt-1 ${bodyClass}`}>{copy.action}</p> : null}
      {copy.technical ? <p className={`mt-1 font-mono text-xs ${codeClass}`}>{code}</p> : null}
    </li>
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
