import type { WalletReadiness } from "@/types/wallet";

export type GeoblockStatus = {
  blocked: boolean;
  checked: boolean;
  raw_response: Record<string, unknown>;
};

export type TradingReadiness = {
  wallet: WalletReadiness;
  geoblock: GeoblockStatus;
  paper_trading_enabled: boolean;
  trading_enabled: boolean;
  kill_switch_active: boolean;
  real_order_dry_run: boolean;
  trading_ready: boolean;
  paper_trading_ready: boolean;
  dry_run_trading_ready: boolean;
  real_trading_ready: boolean;
  real_trading_available: boolean;
  blocking_reasons: string[];
  real_trading_blocking_reasons: string[];
  warnings: string[];
};

export type TradingStatus = {
  trading_enabled: boolean;
  kill_switch_active: boolean;
  real_order_dry_run: boolean;
  mode: "dry_run" | "real" | string;
};
