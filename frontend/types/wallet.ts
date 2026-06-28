export type WalletStatus = {
  configured: boolean;
  wallet_address: string | null;
  funder_address: string | null;
  signature_type: number | null;
  chain_id: number | null;
  api_key_configured: boolean;
  api_key_masked: string | null;
  last_validated_at: string | null;
  last_error: string | null;
  updated_at: string | null;
};

export type WalletConfigurePayload = {
  private_key: string;
  funder_address?: string | null;
  signature_type: number;
  chain_id: number;
  derive_api_credentials: boolean;
};

export type WalletTestResponse = {
  ok: boolean;
  message: string;
  wallet_address: string | null;
  api_key_configured: boolean;
  trading_ready: boolean;
  issues: string[];
};

export type WalletReadiness = {
  wallet_configured: boolean;
  api_credentials_configured: boolean;
  private_key_decryptable: boolean;
  funder_address_configured: boolean;
  signature_type: number | null;
  chain_id: number | null;
  trading_ready: boolean;
  blocking_reasons: string[];
};
