"use client";

import { create } from "zustand";

import type { CurrentMarketOrderbook, HealthResponse, Market } from "@/types/market";
import type { PnlSummary } from "@/types/pnl";
import type {
  BotStatus,
  BtcPriceTick,
  DashboardWsEvent,
  MarketTick,
  OrderUpdate,
  RiskStatus,
  StrategyDecision,
} from "@/types/websocket";

type ConnectionState = "idle" | "connecting" | "connected" | "disconnected";

type DashboardState = {
  health: HealthResponse | null;
  market: Market | null;
  orderbook: CurrentMarketOrderbook | null;
  marketTicks: Record<string, MarketTick>;
  btcPriceTick: BtcPriceTick | null;
  botStatus: BotStatus | null;
  riskStatus: RiskStatus | null;
  pnlSummary: PnlSummary | null;
  currentDecision: StrategyDecision | null;
  lastOrderUpdate: OrderUpdate | null;
  connectionState: ConnectionState;
  lastError: string | null;
  setInitialData: (data: {
    health?: HealthResponse | null;
    market?: Market | null;
    orderbook?: CurrentMarketOrderbook | null;
  }) => void;
  setConnectionState: (state: ConnectionState) => void;
  setError: (message: string | null) => void;
  applyWsEvent: (event: DashboardWsEvent) => void;
};

export const useDashboardStore = create<DashboardState>((set) => ({
  health: null,
  market: null,
  orderbook: null,
  marketTicks: {},
  btcPriceTick: null,
  botStatus: null,
  riskStatus: null,
  pnlSummary: null,
  currentDecision: null,
  lastOrderUpdate: null,
  connectionState: "idle",
  lastError: null,
  setInitialData: (data) =>
    set((state) => ({
      health: data.health ?? state.health,
      market: data.market ?? state.market,
      orderbook: data.orderbook ?? state.orderbook,
    })),
  setConnectionState: (connectionState) => set({ connectionState }),
  setError: (lastError) => set({ lastError }),
  applyWsEvent: (event) =>
    set((state) => {
      switch (event.type) {
        case "market_tick":
          return {
            marketTicks: {
              ...state.marketTicks,
              [event.data.token_id]: event.data,
            },
          };
        case "btc_price_tick":
          return { btcPriceTick: event.data };
        case "bot_status":
          return { botStatus: event.data };
        case "risk_status":
          return { riskStatus: event.data };
        case "pnl_summary":
          return { pnlSummary: event.data };
        case "strategy_decision":
          return { currentDecision: event.data };
        case "order_update":
          return { lastOrderUpdate: event.data };
        case "error":
          return { lastError: event.data.message };
        default:
          return state;
      }
    }),
}));
