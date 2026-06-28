export type StrategySettings = {
  id: number;
  paper_trading_enabled: boolean;
  trading_enabled: boolean;
  kill_switch_active: boolean;
  final_window_seconds: number;
  min_edge: string;
  max_spread: string;
  max_slippage: string;
  max_order_size_usd: string;
  max_daily_loss_usd: string;
  max_data_age_seconds: number;
  order_type: "GTC" | "FOK" | "GTD" | "FAK";
  updated_at: string;
};

export type StrategySettingsPatch = Partial<
  Pick<
    StrategySettings,
    | "paper_trading_enabled"
    | "trading_enabled"
    | "kill_switch_active"
    | "final_window_seconds"
    | "min_edge"
    | "max_spread"
    | "max_slippage"
    | "max_order_size_usd"
    | "max_daily_loss_usd"
    | "max_data_age_seconds"
    | "order_type"
  >
>;

export type StrategyDecision = {
  id: number;
  market_id: number;
  decision: "BUY_UP" | "BUY_DOWN" | "NO_TRADE" | string;
  outcome: "UP" | "DOWN" | null | string;
  mode: "paper" | "real" | string;
  time_remaining_seconds: number | null;
  btc_start_price: string | null;
  current_price: string | null;
  delta: string | null;
  up_bid: string | null;
  up_ask: string | null;
  down_bid: string | null;
  down_ask: string | null;
  estimated_probability: string | null;
  market_price: string | null;
  compared_up_value?: string | null;
  compared_down_value?: string | null;
  price_gap?: string | null;
  edge: string | null;
  spread: string | null;
  risk_passed: boolean;
  risk_reasons: string[];
  reason: string | null;
  raw_context: Record<string, unknown>;
  created_at: string;
};
