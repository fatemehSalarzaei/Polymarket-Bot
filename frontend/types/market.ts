export type HealthResponse = {
  status: string;
  environment: string;
  trading_enabled: boolean;
};

export type Market = {
  id: number;
  event_slug: string;
  market_slug: string | null;
  condition_id: string;
  question: string | null;
  active: boolean;
  closed: boolean;
  start_ts: number | null;
  end_ts: number | null;
  up_token_id: string;
  down_token_id: string;
  created_at: string;
  updated_at: string;
};

export type OrderbookLevel = {
  price: string;
  size: string;
};

export type OrderbookSnapshot = {
  id: number;
  token_id: string;
  outcome: "UP" | "DOWN" | string;
  source_timestamp: string | null;
  received_at: string;
  book_hash: string | null;
  best_bid: string | null;
  best_ask: string | null;
  midpoint: string | null;
  spread: string | null;
  last_trade_price: string | null;
  min_order_size: string | null;
  tick_size: string | null;
  neg_risk: boolean | null;
  bids: OrderbookLevel[];
  asks: OrderbookLevel[];
};

export type CurrentMarketOrderbook = {
  market_id: number;
  event_slug: string;
  up: OrderbookSnapshot;
  down: OrderbookSnapshot;
};

