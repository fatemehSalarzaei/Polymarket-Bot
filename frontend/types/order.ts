export type Order = {
  id: number;
  market_id: number;
  strategy_decision_id: number | null;
  mode: "paper" | "real" | string;
  external_order_id: string | null;
  token_id: string;
  outcome: "UP" | "DOWN" | string;
  side: "BUY" | "SELL" | string;
  order_type: string;
  price: string;
  size: string;
  size_matched: string;
  status: string;
  submitted_at: string;
  updated_at: string;
  filled_at: string | null;
  raw_response: Record<string, unknown>;
  error_message: string | null;
};

