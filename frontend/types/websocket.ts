export type MarketTick = {
  token_id: string;
  event_type: string | null;
  best_bid: string | null;
  best_ask: string | null;
  spread: string | null;
  raw_payload: Record<string, unknown>;
  received_at: string;
};

export type BtcPriceTick = {
  symbol: string;
  value: string;
  source: string;
  source_timestamp: string | null;
  received_at: string;
  raw_payload: Record<string, unknown>;
};

export type StrategyDecision = Record<string, unknown>;
export type OrderUpdate = Record<string, unknown>;

export type BotStatus = {
  running: boolean;
  market_ws_fresh?: boolean;
  rtds_fresh?: boolean;
  background_workers_required?: boolean;
  message?: string | null;
};

export type RiskStatus = {
  trading_enabled: boolean;
  kill_switch_active: boolean;
  geoblock_blocked?: boolean | null;
};

export type DashboardWsEvent =
  | { type: "market_tick"; data: MarketTick }
  | { type: "btc_price_tick"; data: BtcPriceTick }
  | { type: "strategy_decision"; data: StrategyDecision }
  | { type: "order_update"; data: OrderUpdate }
  | { type: "bot_status"; data: BotStatus }
  | { type: "risk_status"; data: RiskStatus }
  | { type: "pnl_summary"; data: PnlSummary }
  | { type: "error"; data: { code: string; message: string } };
import type { PnlSummary } from "@/types/pnl";

