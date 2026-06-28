"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { getCurrentMarket, getCurrentMarketOrderbook, getHealth, getRedeems } from "@/lib/api-client";
import { connectDashboardWebSocket } from "@/lib/websocket-client";
import { useDashboardStore } from "@/stores/dashboard-store";
import { FreshnessBadge } from "@/components/ui/freshness-badge";
import { MetricCard } from "@/components/dashboard/metric-card";
import { RedeemPanel } from "@/components/dashboard/redeem-panel";
import { ApiError } from "@/types/error";
import type { StructuredError } from "@/types/error";
import type { RedeemRecord } from "@/types/redeem";
import type { RuntimeStatus } from "@/types/websocket";

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
    lastOrderUpdate,
    rtdsStatus,
    marketWsStatus,
    lastStructuredError,
    connectionState,
    setInitialData,
    setConnectionState,
    setError,
    setStructuredError,
    applyWsEvent,
  } = useDashboardStore();
  const [loading, setLoading] = useState(true);
  const [redeems, setRedeems] = useState<RedeemRecord[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function loadInitialData() {
      setLoading(true);
      const [healthResult, marketResult, orderbookResult, redeemResult] = await Promise.allSettled([
        getHealth(),
        getCurrentMarket(),
        getCurrentMarketOrderbook(),
        getRedeems(),
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
      if (redeemResult.status === "fulfilled") {
        setRedeems(redeemResult.value);
      }

      for (const result of [healthResult, marketResult, orderbookResult, redeemResult]) {
        if (result.status === "rejected") {
          const message = result.reason instanceof Error ? result.reason.message : "Dashboard data failed to load";
          setError(message);
          if (result.reason instanceof ApiError) {
            setStructuredError(result.reason.structured);
          }
          toast.error(message);
        }
      }

      setLoading(false);
    }

    loadInitialData();
    return () => {
      cancelled = true;
    };
  }, [setError, setInitialData, setStructuredError]);

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

      <StrategySummary
        decision={currentDecision}
        chainlinkAvailable={Boolean(btcPriceTick)}
        paperOrderStatus={readString(lastOrderUpdate, "status") ?? "no paper order"}
      />

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <MarketSideCard
          label="UP"
          tokenId={market?.up_token_id}
          bestBid={upTick?.best_bid ?? orderbook?.up.best_bid}
          bestAsk={upTick?.best_ask ?? orderbook?.up.best_ask}
          midpoint={upTick?.midpoint}
          spread={upTick?.spread ?? orderbook?.up.spread}
          lastTrade={upTick?.last_trade_price}
          dataSource={upTick?.data_source ?? "snapshot"}
          timestamp={upTick?.received_at ?? orderbook?.up.received_at}
        />
        <MarketSideCard
          label="DOWN"
          tokenId={market?.down_token_id}
          bestBid={downTick?.best_bid ?? orderbook?.down.best_bid}
          bestAsk={downTick?.best_ask ?? orderbook?.down.best_ask}
          midpoint={downTick?.midpoint}
          spread={downTick?.spread ?? orderbook?.down.spread}
          lastTrade={downTick?.last_trade_price}
          dataSource={downTick?.data_source ?? "snapshot"}
          timestamp={downTick?.received_at ?? orderbook?.down.received_at}
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <StatusPanel label="Market Stream" status={marketWsStatus} />
        <StatusPanel label="BTC Chainlink RTDS" status={rtdsStatus} />
        <DiagnosticsPanel error={lastStructuredError} />
      </div>

      <RedeemPanel redeems={redeems} />
    </section>
  );
}

function StrategySummary({
  chainlinkAvailable,
  decision,
  paperOrderStatus,
}: {
  chainlinkAvailable: boolean;
  decision: Record<string, unknown> | null;
  paperOrderStatus: string;
}) {
  const raw = readRecord(decision, "raw_context");
  const selectedSide = readString(raw, "selected_side") ?? readString(decision, "outcome") ?? "-";
  const upAsk = readString(decision, "up_ask") ?? readString(raw, "compared_up_value");
  const downAsk = readString(decision, "down_ask") ?? readString(raw, "compared_down_value");
  const priceGap = readString(decision, "price_gap") ?? readString(raw, "price_gap");
  const strategyName = readString(raw, "strategy_name") ?? "FINAL_3M_HIGHER_MARKET_PRICE";
  const reason = readString(decision, "reason");

  return (
    <div className="mt-6 rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-medium uppercase text-muted">Active Strategy</p>
        <p className="text-sm font-semibold text-ink">{strategyName}</p>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MiniMetric label="UP Ask" value={formatPrice(upAsk)} />
        <MiniMetric label="DOWN Ask" value={formatPrice(downAsk)} />
        <MiniMetric label="Selected Side" value={selectedSide} />
        <MiniMetric label="Price Gap" value={formatPrice(priceGap)} />
        <MiniMetric label="Time Remaining" value={formatSeconds(readNumber(decision, "time_remaining_seconds"))} />
        <MiniMetric label="Reason" value={reason ?? "-"} />
        <MiniMetric label="Paper Order Status" value={paperOrderStatus} />
        <MiniMetric label="Chainlink" value="Not required" />
      </div>
      {decision ? (
        <p className="mt-3 text-sm text-zinc-600">{reasonMessage(reason)}</p>
      ) : (
        <p className="mt-3 text-sm text-zinc-600">
          No strategy decision has been recorded yet. The strategy will evaluate when market and orderbook data are
          available.
        </p>
      )}
      {!chainlinkAvailable ? (
        <p className="mt-2 text-xs text-muted">
          Chainlink BTC data is unavailable, but this strategy does not require it.
        </p>
      ) : null}
    </div>
  );
}

function MarketSideCard({
  label,
  tokenId,
  bestBid,
  bestAsk,
  midpoint,
  spread,
  lastTrade,
  dataSource,
  timestamp,
}: {
  label: string;
  tokenId?: string;
  bestBid?: string | null;
  bestAsk?: string | null;
  midpoint?: string | null;
  spread?: string | null;
  lastTrade?: string | null;
  dataSource?: string | null;
  timestamp?: string | null;
}) {
  const displayedProbability = chooseProbability({ midpoint, spread, lastTrade, bestBid, bestAsk });

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase text-muted">{label}</p>
          <p className="mt-1 truncate text-sm text-zinc-600">{tokenId ?? "token unavailable"}</p>
        </div>
        <FreshnessBadge timestamp={timestamp} />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-3">
        <MiniMetric label="Best Bid / Sell" value={formatPrice(bestBid)} />
        <MiniMetric label="Best Ask / Buy" value={formatPrice(bestAsk)} />
        <MiniMetric label="Midpoint" value={formatPrice(midpoint)} />
        <MiniMetric label="Spread" value={formatPrice(spread)} />
        <MiniMetric label="Last Trade" value={formatPrice(lastTrade)} />
        <MiniMetric label="Display Probability" value={formatPrice(displayedProbability)} />
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span>Freshness age: {formatAge(timestamp)}</span>
        <span>Data source: {dataSource ?? "unknown"}</span>
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

function StatusPanel({ label, status }: { label: string; status: RuntimeStatus | null }) {
  const state = status?.status ?? "unknown";
  const tone =
    state === "connected" || state === "subscribed"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : state === "reconnecting" || state === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-700"
        : "border-zinc-200 bg-white text-zinc-600";

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <div className="mt-2 flex items-center justify-between gap-3">
        <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${tone}`}>{state}</span>
        <span className="text-xs text-muted">{formatAge(status?.last_tick_received_at ?? status?.timestamp)}</span>
      </div>
      {status?.message ? <p className="mt-3 text-sm text-zinc-600">{status.message}</p> : null}
    </div>
  );
}

function DiagnosticsPanel({ error }: { error: StructuredError | null }) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <p className="text-xs font-medium uppercase text-muted">Diagnostics</p>
      {error ? (
        <div className="mt-2 space-y-2 text-sm text-zinc-700">
          <p className="font-semibold text-ink">{error.title}</p>
          <p>{error.message}</p>
          {error.technical_detail ? <p className="text-xs text-muted">{error.technical_detail}</p> : null}
          {error.recovery_actions.length > 0 ? (
            <ul className="list-disc space-y-1 pl-4 text-xs text-muted">
              {error.recovery_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-sm text-zinc-600">No structured runtime errors reported.</p>
      )}
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

function formatSeconds(value?: number | null) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${value}s`;
}

function reasonMessage(reason?: string | null) {
  switch (reason) {
    case "ORDERBOOK_DATA_MISSING":
      return "The strategy cannot evaluate because UP or DOWN orderbook data is not available yet. Start the market data worker and wait for a fresh orderbook snapshot.";
    case "NOT_IN_FINAL_WINDOW":
      return "The strategy is waiting for the final 3-minute window.";
    case "PRICE_GAP_TOO_SMALL":
      return "The difference between UP and DOWN prices is below the configured Min Price Gap.";
    case "MARKET_DATA_STALE":
      return "The latest UP/DOWN orderbook data is stale. Wait for a fresh snapshot from the market data worker.";
    case "SPREAD_TOO_HIGH":
      return "The selected side spread is above the configured Max Spread.";
    case "PAPER_TRADING_DISABLED":
      return "Paper trading is disabled, so no paper order will be created.";
    case "KILL_SWITCH_ACTIVE":
      return "Kill Switch is enabled, so no paper or real order will be created.";
    default:
      return reason ? reason.replaceAll("_", " ") : "-";
  }
}

function readRecord(value: Record<string, unknown> | null | undefined, key: string) {
  const next = value?.[key];
  return next && typeof next === "object" && !Array.isArray(next) ? (next as Record<string, unknown>) : null;
}

function readString(value: Record<string, unknown> | null | undefined, key: string) {
  const next = value?.[key];
  if (typeof next === "string") {
    return next;
  }
  if (typeof next === "number") {
    return String(next);
  }
  return null;
}

function readNumber(value: Record<string, unknown> | null | undefined, key: string) {
  const next = value?.[key];
  return typeof next === "number" ? next : null;
}

function chooseProbability({
  midpoint,
  spread,
  lastTrade,
  bestBid,
  bestAsk,
}: {
  midpoint?: string | null;
  spread?: string | null;
  lastTrade?: string | null;
  bestBid?: string | null;
  bestAsk?: string | null;
}) {
  const parsedSpread = Number(spread);
  if (!Number.isNaN(parsedSpread) && parsedSpread > 0.1 && lastTrade) {
    return lastTrade;
  }
  if (midpoint) {
    return midpoint;
  }
  const bid = Number(bestBid);
  const ask = Number(bestAsk);
  if (!Number.isNaN(bid) && !Number.isNaN(ask)) {
    return ((bid + ask) / 2).toString();
  }
  return lastTrade ?? null;
}

function formatAge(timestamp?: string | null) {
  if (!timestamp) {
    return "-";
  }
  const parsed = new Date(timestamp).getTime();
  if (Number.isNaN(parsed)) {
    return "-";
  }
  const ageSeconds = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
  return `${ageSeconds}s`;
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
