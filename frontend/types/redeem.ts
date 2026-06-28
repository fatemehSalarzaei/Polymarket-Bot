export type RedeemStatus =
  | "NOT_ELIGIBLE"
  | "READY_TO_REDEEM"
  | "REDEEM_SUBMITTED"
  | "REDEEM_CONFIRMED"
  | "REDEEM_FAILED"
  | "SKIPPED_DRY_RUN"
  | "SKIPPED_PAPER_ONLY";

export interface RedeemRecord {
  id: number;
  market_id: number;
  settlement_id: number | null;
  condition_id: string;
  winning_outcome: string;
  status: RedeemStatus;
  mode: string;
  tx_hash: string | null;
  wallet_address: string | null;
  amount_redeemed: string | null;
  balance_before: string | null;
  balance_after: string | null;
  error_message: string | null;
  raw_response: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RedeemStatusResponse {
  market_id: number;
  condition_id: string;
  winning_outcome: string | null;
  status: RedeemStatus;
  tx_hash: string | null;
  amount_redeemed: string | null;
  balance_before: string | null;
  balance_after: string | null;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
  real_winning_order_exists: boolean;
  reasons: string[];
}

export interface RedeemAttemptResult {
  market_id: number;
  condition_id: string;
  winning_outcome: string;
  status: RedeemStatus;
  record: RedeemRecord | null;
  tx_hash: string | null;
  amount_redeemed: string | null;
  balance_before: string | null;
  balance_after: string | null;
  error_message: string | null;
  reasons: string[];
}
