export type ReadinessMessage = {
  title: string;
  message: string;
  action?: string;
  technical?: boolean;
};

const messages: Record<string, ReadinessMessage> = {
  WALLET_CONFIG_MISSING: {
    title: "Wallet is not configured",
    message: "Add your wallet private key on the Wallet page before enabling trading execution.",
  },
  WALLET_API_CREDENTIALS_MISSING: {
    title: "API credentials are missing",
    message: "Save your wallet again and let the backend derive Polymarket API credentials.",
  },
  WALLET_FUNDER_REQUIRED: {
    title: "Deposit wallet address is required",
    message: "Deposit/proxy wallet mode needs a funder address before trading can run.",
    action: "Open Advanced Wallet Settings and add the funder address, or switch to simple EOA mode.",
  },
  WALLET_CHAIN_ID_INVALID: {
    title: "Invalid network",
    message: "Trading must use Polygon chain id 137.",
  },
  KILL_SWITCH_ACTIVE: {
    title: "Kill switch is active",
    message: "Trading execution is paused until the kill switch is disabled.",
  },
  GEOBLOCK_BLOCKED: {
    title: "Real trading is unavailable from this backend location",
    message: "Polymarket reports this backend location as restricted. This is a hard blocker for real-money trading.",
    action: "Use paper/dry-run mode, or deploy the backend only in a legally allowed location.",
  },
  GEOBLOCK_CHECK_FAILED: {
    title: "Geoblock check failed",
    message: "The backend could not confirm whether real trading is allowed from this location.",
    action: "Keep using paper/dry-run mode until the check succeeds.",
  },
  REAL_TRADING_ENV_DISABLED: {
    title: "Real trading is disabled on the backend",
    message: "Backend environment variables currently block real order execution.",
    action: "Real mode requires TRADING_ENABLED=true and REAL_TRADING_CONFIRMATION_ENABLED=true.",
  },
  REAL_ORDER_DRY_RUN_ACTIVE: {
    title: "Dry-run mode is active",
    message: "The backend is configured to simulate real-order execution instead of submitting live orders.",
  },
};

export function readinessMessage(code: string): ReadinessMessage {
  return (
    messages[code] ?? {
      title: "Trading is blocked",
      message: "A backend safety check is blocking trading.",
      technical: true,
    }
  );
}
