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
    if (path.endsWith("/trading/readiness")) {
      await route.fulfill({ json: tradingReadinessFixture });
      return;
    }
    if (path.endsWith("/trading/status")) {
      await route.fulfill({
        json: { trading_enabled: false, kill_switch_active: false, real_order_dry_run: true, mode: "dry_run" },
      });
      return;
    }
    if (path.endsWith("/trading/enable")) {
      const body = route.request().postDataJSON();
      await route.fulfill({
        json: {
          trading_enabled: body.confirm_phrase === "ENABLE REAL TRADING",
          kill_switch_active: false,
          real_order_dry_run: true,
          mode: "dry_run",
        },
      });
      return;
    }
    if (path.endsWith("/trading/disable")) {
      await route.fulfill({ json: { trading_enabled: false, kill_switch_active: false, real_order_dry_run: true, mode: "dry_run" } });
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
    if (path.endsWith("/redeems")) {
      await route.fulfill({ json: [] });
      return;
    }
    if (path.endsWith("/wallet/configure")) {
      await route.fulfill({ json: walletConfiguredFixture });
      return;
    }
    if (path.endsWith("/wallet/derive-api-credentials")) {
      await route.fulfill({ json: walletConfiguredFixture });
      return;
    }
    if (path.endsWith("/wallet/test")) {
      await route.fulfill({ json: walletTestFixture });
      return;
    }
    if (path.endsWith("/wallet")) {
      if (route.request().method() === "DELETE") {
        await route.fulfill({ json: walletEmptyFixture });
        return;
      }
      await route.fulfill({ json: walletConfiguredFixture });
      return;
    }

    await route.fulfill({ status: 404, json: { detail: "not mocked" } });
  });
});

test("dashboard loads", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Real Trading")).toBeVisible();
  await expect(page.getByText("Best Bid / Sell").first()).toBeVisible();
  await expect(page.getByText("Best Ask / Buy").first()).toBeVisible();
  await expect(page.getByText("Display Probability").first()).toBeVisible();
  await expect(page.getByText("Diagnostics")).toBeVisible();
  await expect(page.getByText("FINAL_3M_HIGHER_MARKET_PRICE")).toBeVisible();
  await expect(page.getByText("HIGHER_UP_MARKET_PRICE")).toBeVisible();
  await expect(page.getByText("Not required")).toBeVisible();
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

test("wallet page renders status", async ({ page }) => {
  await page.goto("/wallet");
  await expect(page.getByRole("heading", { name: "Polymarket Credentials" })).toBeVisible();
  await expect(page.getByText(maskAddress(walletConfiguredFixture.wallet_address))).toBeVisible();
  await expect(page.getByText(walletConfiguredFixture.api_key_masked)).toBeVisible();
});

test("wallet configure form posts and never displays private key", async ({ page }) => {
  const privateKey = "0x0000000000000000000000000000000000000000000000000000000000000001";
  await page.goto("/wallet");
  await page.getByLabel("Private Key").fill(privateKey);
  await expect(page.getByText("Advanced wallet settings")).toBeVisible();
  await page.getByRole("button", { name: "Save Wallet" }).click();
  await expect(page.getByText("Wallet configuration saved")).toBeVisible();
  await expect(page.getByLabel("Private Key")).toHaveValue("");
  await expect(page.getByText(privateKey)).toHaveCount(0);
});

test("trading enable uses confirmation modal without typed phrase", async ({ page }) => {
  await page.goto("/trading");
  await expect(page.getByText("Confirmation phrase")).toHaveCount(0);
  await page.getByRole("button", { name: "Enable dry-run trading" }).click();
  await expect(page.getByText("Orders will be simulated.")).toBeVisible();
  await page.getByRole("button", { name: "Yes, enable dry-run trading" }).click();
  await expect(page.getByText("Dry-run trading setting enabled")).toBeVisible();
});

test("wallet test and delete buttons call backend", async ({ page }) => {
  await page.goto("/wallet");
  await page.getByRole("button", { name: "Test Credentials" }).click();
  await expect(page.getByText(walletTestFixture.message)).toBeVisible();
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Wallet configuration deleted")).toBeVisible();
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
  min_edge: "0.0500",
  max_spread: "0.0300",
  max_slippage: "0.0200",
  max_order_size_usd: "1.00",
  max_daily_loss_usd: "1.00",
  max_data_age_seconds: 10,
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
  up_ask: "0.90000000",
  down_bid: "0.48000000",
  down_ask: "0.11000000",
  estimated_probability: "0.65000000",
  market_price: "0.90000000",
  edge: "0.79000000",
  spread: "0.01000000",
  risk_passed: true,
  risk_reasons: [],
  reason: "HIGHER_UP_MARKET_PRICE",
  raw_context: {
    strategy_name: "FINAL_3M_HIGHER_MARKET_PRICE",
    selected_side: "UP",
    compared_up_value: "0.90000000",
    compared_down_value: "0.11000000",
    price_gap: "0.79000000",
  },
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

const walletConfiguredFixture = {
  configured: true,
  wallet_address: "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
  funder_address: null,
  signature_type: 0,
  chain_id: 137,
  api_key_configured: true,
  api_key_masked: "api-ke...1234",
  last_validated_at: "2026-06-27T12:30:00Z",
  last_error: null,
  updated_at: "2026-06-27T12:30:00Z",
};

function maskAddress(value: string) {
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

const walletEmptyFixture = {
  configured: false,
  wallet_address: null,
  funder_address: null,
  signature_type: null,
  chain_id: null,
  api_key_configured: false,
  api_key_masked: null,
  last_validated_at: null,
  last_error: null,
  updated_at: null,
};

const walletTestFixture = {
  ok: true,
  message: "Wallet credentials are configured.",
  wallet_address: walletConfiguredFixture.wallet_address,
  api_key_configured: true,
  trading_ready: true,
  issues: [],
};

const tradingReadinessFixture = {
  wallet: {
    wallet_configured: true,
    api_credentials_configured: true,
    private_key_decryptable: true,
    funder_address_configured: false,
    signature_type: 0,
    chain_id: 137,
    trading_ready: true,
    blocking_reasons: [],
  },
  geoblock: { blocked: false, checked: true, raw_response: {} },
  paper_trading_enabled: true,
  trading_enabled: false,
  kill_switch_active: false,
  real_order_dry_run: true,
  trading_ready: true,
  paper_trading_ready: true,
  dry_run_trading_ready: true,
  real_trading_ready: false,
  real_trading_available: false,
  blocking_reasons: [],
  real_trading_blocking_reasons: ["REAL_ORDER_DRY_RUN_ACTIVE"],
  warnings: [],
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
