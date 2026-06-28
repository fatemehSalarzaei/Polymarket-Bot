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
  blocking_reasons: string[];
};

export type TradingStatus = {
  trading_enabled: boolean;
  kill_switch_active: boolean;
  real_order_dry_run: boolean;
};
