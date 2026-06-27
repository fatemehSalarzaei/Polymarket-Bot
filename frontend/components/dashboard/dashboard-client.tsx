"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { getCurrentMarket, getCurrentMarketOrderbook, getHealth } from "@/lib/api-client";
import { connectDashboardWebSocket } from "@/lib/websocket-client";
import { useDashboardStore } from "@/stores/dashboard-store";
import { FreshnessBadge } from "@/components/ui/freshness-badge";
import { MetricCard } from "@/components/dashboard/metric-card";

export function DashboardClient() {
  const {
    health,
    market,
    orderbook,
    marketTicks,
    btcPriceTick,
    botStatus,
    riskStatus,
    currentDecision,
    connectionState,
    setInitialData,
    setConnectionState,
    setError,
    applyWsEvent,
  } = useDashboardStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialData() {
      setLoading(true);
      const [healthResult, marketResult, orderbookResult] = await Promise.allSettled([
        getHealth(),
        getCurrentMarket(),
        getCurrentMarketOrderbook(),
      ]);

      if (cancelled) {
        return;
      }

      const nextData = {
        health: healthResult.status === "fulfilled" ? healthResult.value : null,
        market: marketResult.status === "fulfilled" ? marketResult.value : null,
        orderbook: orderbookResult.status === "fulfilled" ? orderbookResult.value : null,
      };
      setInitialData(nextData);

      for (const result of [healthResult, marketResult, orderbookResult]) {
        if (result.status === "rejected") {
          const message = result.reason instanceof Error ? result.reason.message : "Dashboard data failed to load";
          setError(message);
          toast.error(message);
        }
      }

      setLoading(false);
    }

    loadInitialData();
    return () => {
      cancelled = true;
    };
  }, [setError, setInitialData]);

  useEffect(() => {
    setConnectionState("connecting");
    return connectDashboardWebSocket({
      onOpen: () => setConnectionState("connected"),
      onClose: () => setConnectionState("disconnected"),
      onError: (message) => {
        setError(message);
        toast.error(message);
      },
      onEvent: (event) => {
        applyWsEvent(event);
        if (event.type === "error") {
          toast.error(event.data.message);
        }
      },
    });
  }, [applyWsEvent, setConnectionState, setError]);

  const upTick = market ? marketTicks[market.up_token_id] : undefined;
  const downTick = market ? marketTicks[market.down_token_id] : undefined;
  const countdown = useCountdown(market?.end_ts ?? (market?.start_ts ? market.start_ts + 900 : null));
  const btcValue = btcPriceTick?.value ?? "-";
  const tradingEnabled = riskStatus?.trading_enabled ?? health?.trading_enabled ?? false;

  const marketSlug = market?.event_slug ?? (loading ? "Loading..." : "Unavailable");
  const decisionLabel = useMemo(() => {
    const decision = currentDecision?.decision;
    return typeof decision === "string" ? decision : "NO_DATA";
  }, [currentDecision]);

  return (
    <section className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-6 flex flex-col gap-2">
        <p className="text-sm font-semibold text-accent">Monitoring first, paper trading by default</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <h2 className="text-3xl font-bold tracking-normal">Dashboard</h2>
          <div className="flex items-center gap-2 text-sm text-muted">
            <span>WS</span>
            <span
              className={`rounded-md border px-2 py-1 text-xs font-semibold ${
                connectionState === "connected"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-zinc-200 bg-white text-zinc-600"
              }`}
            >
              {connectionState}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Bot Status" value={botStatus?.running ? "running" : "idle"} detail={health?.environment} />
        <MetricCard label="Current Market" value={marketSlug} detail={market?.question ?? undefined} />
        <MetricCard label="Countdown" value={countdown} detail="15m cycle" />
        <MetricCard
          label="Real Trading"
          value={tradingEnabled ? "enabled" : "disabled"}
          tone={tradingEnabled ? "bad" : "good"}
          detail={riskStatus?.kill_switch_active ? "kill switch active" : "safe default"}
        />
        <MetricCard label="Chainlink BTC/USD" value={formatUsd(btcValue)} detail={btcPriceTick?.symbol ?? "btc/usd"} />
        <MetricCard label="BTC Delta" value="-" detail="strategy phase pending" />
        <MetricCard
          label="Current Decision"
          value={decisionLabel}
          tone={decisionLabel === "NO_DATA" || decisionLabel === "NO_TRADE" ? "warning" : "good"}
        />
        <MetricCard label="Paper PnL" value="-" detail="settlement phase pending" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <MarketSideCard
          label="UP"
          tokenId={market?.up_token_id}
          bestBid={upTick?.best_bid ?? orderbook?.up.best_bid}
          bestAsk={upTick?.best_ask ?? orderbook?.up.best_ask}
          spread={upTick?.spread ?? orderbook?.up.spread}
          timestamp={upTick?.received_at ?? orderbook?.up.received_at}
        />
        <MarketSideCard
          label="DOWN"
          tokenId={market?.down_token_id}
          bestBid={downTick?.best_bid ?? orderbook?.down.best_bid}
          bestAsk={downTick?.best_ask ?? orderbook?.down.best_ask}
          spread={downTick?.spread ?? orderbook?.down.spread}
          timestamp={downTick?.received_at ?? orderbook?.down.received_at}
        />
      </div>
    </section>
  );
}

function MarketSideCard({
  label,
  tokenId,
  bestBid,
  bestAsk,
  spread,
  timestamp,
}: {
  label: string;
  tokenId?: string;
  bestBid?: string | null;
  bestAsk?: string | null;
  spread?: string | null;
  timestamp?: string | null;
}) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase text-muted">{label}</p>
          <p className="mt-1 truncate text-sm text-zinc-600">{tokenId ?? "token unavailable"}</p>
        </div>
        <FreshnessBadge timestamp={timestamp} />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3">
        <MiniMetric label="Bid" value={formatPrice(bestBid)} />
        <MiniMetric label="Ask" value={formatPrice(bestAsk)} />
        <MiniMetric label="Spread" value={formatPrice(spread)} />
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold text-ink">{value}</p>
    </div>
  );
}

function useCountdown(endTs: number | null | undefined) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  if (!endTs) {
    return "-";
  }
  const remaining = Math.max(0, endTs * 1000 - now);
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatPrice(value?: string | null) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return parsed.toFixed(3);
}

function formatUsd(value?: string | null) {
  if (!value || value === "-") {
    return "-";
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(parsed);
}

