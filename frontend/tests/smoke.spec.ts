import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.endsWith("/health")) {
      await route.fulfill({ json: { status: "ok", environment: "test", trading_enabled: false } });
      return;
    }
    if (path.endsWith("/markets/current")) {
      await route.fulfill({ json: marketFixture });
      return;
    }
    if (path.endsWith("/markets/current/orderbook")) {
      await route.fulfill({ json: orderbookFixture });
      return;
    }
    if (path.endsWith("/strategy/settings")) {
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON();
        await route.fulfill({ json: { ...settingsFixture, ...body } });
        return;
      }
      await route.fulfill({ json: settingsFixture });
      return;
    }
    if (path.endsWith("/strategy/current-decision")) {
      await route.fulfill({ json: decisionFixture });
      return;
    }
    if (path.endsWith("/strategy/decisions")) {
      await route.fulfill({ json: [decisionFixture] });
      return;
    }
    if (path.endsWith("/orders")) {
      await route.fulfill({ json: [orderFixture] });
      return;
    }
    if (path.endsWith("/pnl/summary")) {
      await route.fulfill({ json: pnlFixture });
      return;
    }
    if (path.endsWith("/logs")) {
      await route.fulfill({ json: [logFixture] });
      return;
    }

    await route.fulfill({ status: 404, json: { detail: "not mocked" } });
  });
});

test("dashboard loads", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Real Trading")).toBeVisible();
});

test("current market loads", async ({ page }) => {
  await page.goto("/markets/current");
  await expect(page.getByRole("heading", { name: "Current Market" })).toBeVisible();
  await expect(page.getByText(marketFixture.event_slug)).toBeVisible();
});

test("strategy settings can be edited", async ({ page }) => {
  await page.goto("/strategy");
  await expect(page.getByRole("heading", { name: "Strategy" })).toBeVisible();
  await page.getByLabel("Final Window Seconds").fill("120");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Strategy settings saved")).toBeVisible();
});

test("orders load", async ({ page }) => {
  await page.goto("/orders");
  await expect(page.getByRole("heading", { name: "Orders" })).toBeVisible();
  await expect(page.getByText("FILLED")).toBeVisible();
});

test("pnl loads", async ({ page }) => {
  await page.goto("/pnl");
  await expect(page.getByRole("heading", { name: "PnL" })).toBeVisible();
  await expect(page.getByText("Settled Markets")).toBeVisible();
});

test("logs load", async ({ page }) => {
  await page.goto("/logs");
  await expect(page.getByRole("heading", { name: "Logs" })).toBeVisible();
  await expect(page.getByText("strategy_settings.patch")).toBeVisible();
});

const marketFixture = {
  id: 1,
  event_slug: "btc-updown-15m-1782563400",
  market_slug: "btc-updown-15m-1782563400-market",
  condition_id: "condition-1",
  question: "BTC Up or Down",
  active: true,
  closed: false,
  start_ts: 1782563400,
  end_ts: 1782564300,
  up_token_id: "up-token",
  down_token_id: "down-token",
  created_at: "2026-06-27T12:30:00Z",
  updated_at: "2026-06-27T12:30:00Z",
};

const orderbookFixture = {
  market_id: 1,
  event_slug: marketFixture.event_slug,
  up: snapshot("UP", "up-token"),
  down: snapshot("DOWN", "down-token"),
};

const settingsFixture = {
  id: 1,
  paper_trading_enabled: true,
  trading_enabled: false,
  kill_switch_active: false,
  final_window_seconds: 180,
  min_edge: "0.0400",
  max_spread: "0.0200",
  max_slippage: "0.0200",
  max_order_size_usd: "10.00",
  max_daily_loss_usd: "50.00",
  max_data_age_seconds: 5,
  order_type: "FAK",
  updated_at: "2026-06-27T12:30:00Z",
};

const decisionFixture = {
  id: 1,
  market_id: 1,
  decision: "BUY_UP",
  outcome: "UP",
  mode: "paper",
  time_remaining_seconds: 120,
  btc_start_price: "100.00000000",
  current_price: "101.00000000",
  delta: "1.00000000",
  up_bid: "0.49000000",
  up_ask: "0.50000000",
  down_bid: "0.48000000",
  down_ask: "0.51000000",
  estimated_probability: "0.65000000",
  market_price: "0.50000000",
  edge: "0.15000000",
  spread: "0.01000000",
  risk_passed: true,
  risk_reasons: [],
  reason: "EDGE_PASSED",
  raw_context: {},
  created_at: "2026-06-27T12:30:00Z",
};

const orderFixture = {
  id: 1,
  market_id: 1,
  strategy_decision_id: 1,
  mode: "paper",
  external_order_id: null,
  token_id: "up-token",
  outcome: "UP",
  side: "BUY",
  order_type: "FAK",
  price: "0.52000000",
  size: "19.23076923",
  size_matched: "19.23076923",
  status: "FILLED",
  submitted_at: "2026-06-27T12:30:00Z",
  updated_at: "2026-06-27T12:30:00Z",
  filled_at: "2026-06-27T12:30:00Z",
  raw_response: { simulated: true },
  error_message: null,
};

const pnlFixture = {
  paper_pnl: "9.23076923",
  real_pnl: "0",
  paper_orders: 1,
  real_orders: 0,
  settled_markets: 1,
  winning_trades: 1,
  losing_trades: 0,
  win_rate: "1",
  no_trade_count: 0,
};

const logFixture = {
  id: 1,
  actor: "dashboard",
  action: "strategy_settings.patch",
  entity_type: "strategy_settings",
  entity_id: "1",
  before: null,
  after: { final_window_seconds: 120 },
  ip_address: "127.0.0.1",
  user_agent: "playwright",
  created_at: "2026-06-27T12:30:00Z",
};

function snapshot(outcome: string, tokenId: string) {
  return {
    id: outcome === "UP" ? 1 : 2,
    token_id: tokenId,
    outcome,
    source_timestamp: "2026-06-27T12:30:00Z",
    received_at: new Date().toISOString(),
    book_hash: `hash-${tokenId}`,
    best_bid: "0.48000000",
    best_ask: "0.51000000",
    midpoint: "0.49500000",
    spread: "0.03000000",
    last_trade_price: "0.50000000",
    min_order_size: "5.00000000",
    tick_size: "0.01000000",
    neg_risk: false,
    bids: [{ price: "0.48", size: "75" }],
    asks: [{ price: "0.51", size: "80" }],
  };
}
