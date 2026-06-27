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
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <LiveTick
          label="UP Live Tick"
          bid={upTick?.best_bid}
          ask={upTick?.best_ask}
          spread={upTick?.spread}
          timestamp={upTick?.received_at}
        />
        <LiveTick
          label="DOWN Live Tick"
          bid={downTick?.best_bid}
          ask={downTick?.best_ask}
          spread={downTick?.spread}
          timestamp={downTick?.received_at}
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
  bid,
  ask,
  spread,
  timestamp,
}: {
  label: string;
  bid?: string | null;
  ask?: string | null;
  spread?: string | null;
  timestamp?: string | null;
}) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">{label}</h3>
        <FreshnessBadge timestamp={timestamp} />
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <Info label="Bid" value={formatNumber(bid)} />
        <Info label="Ask" value={formatNumber(ask)} />
        <Info label="Spread" value={formatNumber(spread)} />
      </div>
    </div>
  );
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

