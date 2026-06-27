# 07 — Strategy and Risk Engine

## Main rule
Do not buy simply because one outcome percentage is higher. Price is cost. Enter only when estimated probability minus entry price is above `min_edge`.

## Decision values
```text
BUY_UP
BUY_DOWN
NO_TRADE
```

## Strategy window
Only evaluate when:
```text
time_remaining_seconds <= final_window_seconds
```
Default: 180 seconds.

## Context required
- market
- time remaining
- BTC start price
- BTC current price
- BTC delta
- Up best bid/ask/spread
- Down best bid/ask/spread
- data age
- settings

## MVP strategy
1. Determine direction from BTC delta:
   - delta > 0 -> candidate UP
   - delta < 0 -> candidate DOWN
   - otherwise NO_TRADE
2. Use best ask as entry price.
3. Estimate probability with conservative rule-based function.
4. Compute:
```text
edge = estimated_probability - entry_price
```
5. Trade only if:
```text
edge >= min_edge
spread <= max_spread
data_fresh == true
liquidity_ok == true
```

## No-trade reasons
- NOT_IN_FINAL_WINDOW
- UNKNOWN_DIRECTION
- EDGE_TOO_LOW
- SPREAD_TOO_HIGH
- LIQUIDITY_TOO_LOW
- MARKET_DATA_STALE
- CHAINLINK_DATA_STALE
- KILL_SWITCH_ACTIVE
- TRADING_DISABLED
- GEOBLOCK_BLOCKED
- DAILY_LOSS_LIMIT_REACHED
- TOKEN_MAPPING_AMBIGUOUS

## Real trading gates
All must pass:
- trading_enabled true
- kill_switch false
- geoblock not blocked
- credentials configured
- max order size respected
- daily loss limit not reached
- data fresh
- strategy edge valid
- order type allowed

## Paper trading
Paper trading should simulate fills using best ask plus configured slippage. Persist all paper orders and later settle PnL.
