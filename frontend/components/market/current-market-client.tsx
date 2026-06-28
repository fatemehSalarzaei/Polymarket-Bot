"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getCurrentMarket, getCurrentMarketOrderbook } from "@/lib/api-client";
import { connectDashboardWebSocket } from "@/lib/websocket-client";
import { useDashboardStore } from "@/stores/dashboard-store";
import { OrderbookTable } from "@/components/market/orderbook-table";
import { FreshnessBadge } from "@/components/ui/freshness-badge";

export function CurrentMarketClient() {
  const { market, orderbook, marketTicks, setInitialData, applyWsEvent, setError } = useDashboardStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const [marketResult, orderbookResult] = await Promise.allSettled([
        getCurrentMarket(),
        getCurrentMarketOrderbook(),
      ]);

      if (cancelled) {
        return;
      }

      setInitialData({
        market: marketResult.status === "fulfilled" ? marketResult.value : null,
        orderbook: orderbookResult.status === "fulfilled" ? orderbookResult.value : null,
      });

      for (const result of [marketResult, orderbookResult]) {
        if (result.status === "rejected") {
          const message = result.reason instanceof Error ? result.reason.message : "Market data failed to load";
          setError(message);
          toast.error(message);
        }
      }

      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [setError, setInitialData]);

  useEffect(() => {
    return connectDashboardWebSocket({
      onEvent: applyWsEvent,
      onError: (message) => {
        setError(message);
        toast.error(message);
      },
    });
  }, [applyWsEvent, setError]);

  const upTick = market ? marketTicks[market.up_token_id] : undefined;
  const downTick = market ? marketTicks[market.down_token_id] : undefined;
  const countdown = useCountdown(market?.end_ts ?? (market?.start_ts ? market.start_ts + 900 : null));
  const upSource = upTick ? "market_ws" : orderbook?.up ? "orderbook_snapshot" : "no_data";
  const downSource = downTick ? "market_ws" : orderbook?.down ? "orderbook_snapshot" : "no_data";

  return (
    <section className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-6">
        <p className="text-sm font-semibold text-accent">Current BTC Up/Down 15m market</p>
        <h2 className="mt-1 text-3xl font-bold tracking-normal">Current Market</h2>
      </div>

      <div className="rounded-md border border-zinc-200 bg-white p-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Info label="Event Slug" value={market?.event_slug ?? (loading ? "Loading..." : "Unavailable")} />
          <Info label="Condition ID" value={market?.condition_id ?? "-"} />
          <Info label="Status" value={market ? (market.active && !market.closed ? "active" : "closed") : "-"} />
          <Info label="Question" value={market?.question ?? "-"} />
          <Info label="Countdown" value={countdown} />
          <Info label="Start Time" value={formatTimestamp(market?.start_ts)} />
          <Info label="End Time" value={formatTimestamp(market?.end_ts)} />
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <LiveTick
          label="UP Live Tick"
          ask={upTick?.best_ask ?? orderbook?.up.best_ask}
          bid={upTick?.best_bid ?? orderbook?.up.best_bid}
          dataSource={upTick?.data_source ?? upSource}
          lastTradePrice={upTick?.last_trade_price ?? orderbook?.up.last_trade_price}
          midpoint={upTick?.midpoint ?? orderbook?.up.midpoint}
          source={upSource}
          spread={upTick?.spread ?? orderbook?.up.spread}
          timestamp={upTick?.received_at ?? orderbook?.up.received_at}
        />
        <LiveTick
          label="DOWN Live Tick"
          ask={downTick?.best_ask ?? orderbook?.down.best_ask}
          bid={downTick?.best_bid ?? orderbook?.down.best_bid}
          dataSource={downTick?.data_source ?? downSource}
          lastTradePrice={downTick?.last_trade_price ?? orderbook?.down.last_trade_price}
          midpoint={downTick?.midpoint ?? orderbook?.down.midpoint}
          source={downSource}
          spread={downTick?.spread ?? orderbook?.down.spread}
          timestamp={downTick?.received_at ?? orderbook?.down.received_at}
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <OrderbookTable title="UP Orderbook" snapshot={orderbook?.up} />
        <OrderbookTable title="DOWN Orderbook" snapshot={orderbook?.down} />
      </div>
    </section>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <p className="mt-1 break-words text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}

function LiveTick({
  label,
  ask,
  bid,
  dataSource,
  lastTradePrice,
  midpoint,
  source,
  spread,
  timestamp,
}: {
  label: string;
  ask?: string | null;
  bid?: string | null;
  dataSource: string;
  lastTradePrice?: string | null;
  midpoint?: string | null;
  source: "market_ws" | "orderbook_snapshot" | "no_data";
  spread?: string | null;
  timestamp?: string | null;
}) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold">{label}</h3>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs font-semibold text-zinc-600">
            {source}
          </span>
          <FreshnessBadge timestamp={timestamp} />
        </div>
      </div>
      {source === "no_data" ? <p className="mt-3 text-sm text-muted">No data yet</p> : null}
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <Info label="Bid" value={formatNumber(bid)} />
        <Info label="Ask" value={formatNumber(ask)} />
        <Info label="Spread" value={formatNumber(spread)} />
        <Info label="Midpoint" value={formatNumber(midpoint)} />
        <Info label="Last Trade" value={formatNumber(lastTradePrice)} />
        <Info label="Data Source" value={dataSource} />
      </div>
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

function formatTimestamp(value?: number | null) {
  if (!value) {
    return "-";
  }
  return new Date(value * 1000).toLocaleString();
}

function formatNumber(value?: string | null) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return parsed.toLocaleString("en-US", { maximumFractionDigits: 4 });
}
