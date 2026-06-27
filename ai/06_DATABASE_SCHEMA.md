# 06 — Database Schema

Use PostgreSQL + SQLAlchemy 2 + Alembic.

## tables

### markets
- id
- event_slug unique
- market_slug
- condition_id
- question/title
- active/closed
- start_ts/end_ts
- up_token_id/down_token_id
- raw_event/raw_market JSONB
- created_at/updated_at

### orderbook_snapshots
- id
- market_id FK
- token_id
- outcome UP/DOWN
- source_timestamp
- received_at
- book_hash
- best_bid/best_ask/midpoint/spread
- last_trade_price
- min_order_size/tick_size/neg_risk
- bids/asks JSONB

### chainlink_ticks
- id
- symbol default btc/usd
- value
- source default polymarket_rtds_chainlink
- source_timestamp
- received_at
- raw_payload JSONB

### strategy_decisions
- id
- market_id FK
- decision BUY_UP/BUY_DOWN/NO_TRADE
- outcome
- mode paper/real
- time_remaining_seconds
- btc_start_price/current_price/delta
- up_bid/up_ask/down_bid/down_ask
- estimated_probability
- market_price
- edge
- spread
- risk_passed
- risk_reasons JSONB
- reason
- raw_context JSONB
- created_at

### orders
- id
- market_id FK
- strategy_decision_id FK
- mode paper/real
- external_order_id
- token_id
- outcome
- side
- order_type
- price
- size
- size_matched
- status
- submitted_at/updated_at/filled_at
- raw_response JSONB
- error_message

### settlements
- id
- market_id FK
- winning_outcome
- btc_start_price/btc_end_price
- resolved_at
- paper_pnl/real_pnl
- raw_resolution JSONB

### strategy_settings
- id
- paper_trading_enabled default true
- trading_enabled default false
- kill_switch_active default false
- final_window_seconds default 180
- min_edge default 0.04
- max_spread default 0.02
- max_slippage default 0.02
- max_order_size_usd default 10
- max_daily_loss_usd default 50
- max_data_age_seconds default 5
- order_type default FAK
- updated_at

### audit_logs
- id
- actor
- action
- entity_type/entity_id
- before/after JSONB
- ip_address/user_agent
- created_at

## Indexes
Add indexes on market time, token_id + received_at, strategy_decisions market_id + created_at, orders mode/status/submitted_at.
