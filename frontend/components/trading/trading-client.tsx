"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { disableTrading, enableTrading, getTradingReadiness } from "@/lib/api-client";
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
          <ul className="mt-3 space-y-3 text-sm">
            {readiness.blocking_reasons.map((reason) => (
              <li key={reason} className="rounded-md border border-red-100 bg-red-50 p-3 text-red-900">
                <p className="font-semibold">{blockerCopy(reason).title}</p>
                <p className="mt-1 text-red-800">{blockerCopy(reason).message}</p>
                {blockerCopy(reason).technical ? <p className="mt-1 font-mono text-xs text-red-700">{reason}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-zinc-600">No blockers reported.</p>
        )}
      </section>
      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="font-semibold text-ink">Real Trading</h2>
        <p className="mt-2 text-sm text-zinc-600">
          Real trading allows the bot to submit real Polymarket orders using your configured wallet.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button className="btn-danger" disabled={enableDisabled(readiness, loading)} onClick={() => setConfirmOpen(true)}>
            Enable real trading
          </button>
          <button className="btn-secondary" disabled={loading} onClick={() => void run("disable")}>
            Disable real trading
          </button>
        </div>
        {enableDisabled(readiness, loading) ? <p className="mt-3 text-sm text-zinc-600">{disabledReason(readiness, loading)}</p> : null}
      </section>
      {confirmOpen ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-md bg-white p-5 shadow-xl">
            <h2 className="text-lg font-semibold text-ink">Enable real trading?</h2>
            <p className="mt-3 text-sm text-zinc-700">
              Are you sure you want to enable real trading? The bot may submit real orders using your configured wallet.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button className="btn-secondary" disabled={loading} onClick={() => setConfirmOpen(false)}>
                Cancel
              </button>
              <button className="btn-danger" disabled={loading} onClick={() => void run("enable")}>
                Yes, enable real trading
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

type BlockerCopy = { title: string; message: string; technical?: boolean };

const blockerMessages: Record<string, BlockerCopy> = {
  WALLET_CONFIG_MISSING: {
    title: "Wallet is not configured",
    message: "Add your wallet private key on the Wallet page.",
  },
  WALLET_API_CREDENTIALS_MISSING: {
    title: "API credentials are missing",
    message: "Save your wallet again and let the backend derive Polymarket API credentials.",
  },
  WALLET_FUNDER_REQUIRED: {
    title: "Deposit wallet address is required",
    message:
      "This is only needed for deposit/proxy wallet mode. Open Advanced Wallet Settings and add the funder/deposit wallet address, or switch to simple EOA mode.",
  },
  WALLET_CHAIN_ID_INVALID: {
    title: "Invalid network",
    message: "Trading must use Polygon chain id 137.",
  },
  KILL_SWITCH_ACTIVE: {
    title: "Kill switch is active",
    message: "Real trading is blocked until the kill switch is disabled.",
  },
  REAL_TRADING_ENV_DISABLED: {
    title: "Real trading is disabled on the backend",
    message: "Backend environment variables currently block real order execution.",
  },
};

function blockerCopy(reason: string) {
  return blockerMessages[reason] ?? { title: "Trading is blocked", message: "A backend safety check is blocking real trading.", technical: true };
}

function enableDisabled(readiness: TradingReadiness | null, loading: boolean) {
  return (
    loading ||
    readiness === null ||
    readiness.trading_ready !== true ||
    readiness.trading_enabled ||
    readiness.kill_switch_active ||
    readiness.wallet.trading_ready !== true
  );
}

function disabledReason(readiness: TradingReadiness | null, loading: boolean) {
  if (loading || readiness === null) {
    return "Checking trading readiness...";
  }
  if (readiness.trading_enabled) {
    return "Real trading is already enabled.";
  }
  if (readiness.kill_switch_active) {
    return "Disable the kill switch before enabling real trading.";
  }
  if (!readiness.wallet.trading_ready) {
    return "Wallet setup is not ready for real trading.";
  }
  if (!readiness.trading_ready) {
    return "Resolve the readiness blockers before enabling real trading.";
  }
  return "";
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase text-zinc-500">{label}</p>
      <p className="mt-2 text-lg font-bold text-ink">{value}</p>
    </div>
  );
}
