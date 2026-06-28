"use client";

import { create } from "zustand";

import type { CurrentMarketOrderbook, HealthResponse, Market } from "@/types/market";
import type { PnlSummary } from "@/types/pnl";
import type { StructuredError } from "@/types/error";
import type {
  BotStatus,
  BtcPriceTick,
  DashboardWsEvent,
  MarketTick,
  OrderUpdate,
  RiskStatus,
  RuntimeStatus,
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
  rtdsStatus: RuntimeStatus | null;
  marketWsStatus: RuntimeStatus | null;
  connectionState: ConnectionState;
  lastError: string | null;
  lastStructuredError: StructuredError | null;
  setInitialData: (data: {
    health?: HealthResponse | null;
    market?: Market | null;
    orderbook?: CurrentMarketOrderbook | null;
  }) => void;
  setConnectionState: (state: ConnectionState) => void;
  setError: (message: string | null) => void;
  setStructuredError: (error: StructuredError | null) => void;
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
  rtdsStatus: null,
  marketWsStatus: null,
  connectionState: "idle",
  lastError: null,
  lastStructuredError: null,
  setInitialData: (data) =>
    set((state) => ({
      health: data.health ?? state.health,
      market: data.market ?? state.market,
      orderbook: data.orderbook ?? state.orderbook,
    })),
  setConnectionState: (connectionState) => set({ connectionState }),
  setError: (lastError) => set({ lastError }),
  setStructuredError: (lastStructuredError) => set({ lastStructuredError }),
  applyWsEvent: (event) =>
    set((state) => {
      switch (event.type) {
        case "current_market":
          return {
            market: event.data,
            marketTicks: {},
            orderbook: event.data.id === state.orderbook?.market_id ? state.orderbook : null,
          };
        case "orderbook_update":
          return { orderbook: event.data };
        case "orderbook_snapshot":
          if (!state.market) {
            return state;
          }
          if (event.data.token_id === state.market.up_token_id) {
            return state.orderbook ? { orderbook: { ...state.orderbook, up: event.data } } : state;
          }
          if (event.data.token_id === state.market.down_token_id && state.orderbook) {
            return { orderbook: { ...state.orderbook, down: event.data } };
          }
          return state;
        case "market_tick":
          return {
            marketTicks: {
              ...state.marketTicks,
              [event.data.token_id]: event.data,
            },
          };
        case "trade_tick":
          return {
            marketTicks: {
              ...state.marketTicks,
              [event.data.token_id]: {
                ...state.marketTicks[event.data.token_id],
                ...event.data,
              },
            },
          };
        case "btc_price_tick":
          return { btcPriceTick: event.data };
        case "rtds_status":
          return { rtdsStatus: event.data };
        case "market_ws_status":
          return { marketWsStatus: event.data };
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
          return { lastError: event.data.message, lastStructuredError: event.data };
        default:
          return state;
      }
    }),
}));
