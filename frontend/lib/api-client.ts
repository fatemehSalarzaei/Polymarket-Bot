import type { CurrentMarketOrderbook, HealthResponse, Market } from "@/types/market";
import type { Order } from "@/types/order";
import type { AuditLog } from "@/types/log";
import type { PnlSummary } from "@/types/pnl";
import type { RedeemAttemptResult, RedeemRecord, RedeemStatusResponse } from "@/types/redeem";
import type { StrategyDecision, StrategySettings, StrategySettingsPatch } from "@/types/strategy";
import type { WalletConfigurePayload, WalletStatus, WalletTestResponse } from "@/types/wallet";
import type { CurrentUser, LoginResponse, User } from "@/types/auth";
import type { TradingReadiness, TradingStatus } from "@/types/trading";
import { ApiError, type StructuredError } from "@/types/error";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
export const REAL_TRADING_CONFIRMATION_PHRASE = "ENABLE REAL TRADING";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    credentials: "include",
    headers: {
      "content-type": "application/json",
      ...init?.headers,
    },
    ...init,
  });
  if (!response.ok) {
    throw await buildApiError(response, path);
  }
  return response.json() as Promise<T>;
}

async function buildApiError(response: Response, path: string): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (isStructuredError(payload)) {
    return new ApiError(payload.message, { status: response.status, path, structured: payload });
  }
  if (isFastApiDetail(payload)) {
    return new ApiError(payload.detail, { status: response.status, path });
  }
  return new ApiError(`Request failed (${response.status}) for ${path}`, { status: response.status, path });
}

function isStructuredError(value: unknown): value is StructuredError {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<StructuredError>;
  return typeof candidate.code === "string" && typeof candidate.message === "string" && typeof candidate.title === "string";
}

function isFastApiDetail(value: unknown): value is { detail: string } {
  return Boolean(value && typeof value === "object" && typeof (value as { detail?: unknown }).detail === "string");
}

export function getHealth() {
  return request<HealthResponse>("/health");
}

export function getCurrentMarket() {
  return request<Market>("/markets/current");
}

export function getCurrentMarketOrderbook() {
  return request<CurrentMarketOrderbook>("/markets/current/orderbook");
}

export function getStrategySettings() {
  return request<StrategySettings>("/strategy/settings");
}

export function patchStrategySettings(patch: StrategySettingsPatch) {
  return request<StrategySettings>("/strategy/settings", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function getCurrentDecision() {
  return request<StrategyDecision>("/strategy/current-decision");
}

export function getDecisionHistory(limit = 100) {
  return request<StrategyDecision[]>(`/strategy/decisions?limit=${limit}`);
}

export function getOrders(limit = 100) {
  return request<Order[]>(`/orders?limit=${limit}`);
}

export function getPnlSummary() {
  return request<PnlSummary>("/pnl/summary");
}

export function getLogs(limit = 100) {
  return request<AuditLog[]>(`/logs?limit=${limit}`);
}

export function getRedeems(limit = 100) {
  return request<RedeemRecord[]>(`/redeems?limit=${limit}`);
}

export function getRedeemByMarket(marketId: number) {
  return request<RedeemStatusResponse>(`/redeems/${marketId}`);
}

export function attemptRedeem(marketId: number) {
  return request<RedeemAttemptResult>(`/redeems/${marketId}/attempt`, {
    method: "POST",
  });
}

export function getWalletStatus() {
  return request<WalletStatus>("/wallet");
}

export function configureWallet(payload: WalletConfigurePayload) {
  return request<WalletStatus>("/wallet/configure", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deriveWalletApiCredentials() {
  return request<WalletStatus>("/wallet/derive-api-credentials", {
    method: "POST",
  });
}

export function testWalletCredentials() {
  return request<WalletTestResponse>("/wallet/test", {
    method: "POST",
  });
}

export function deleteWalletCredentials() {
  return request<WalletStatus>("/wallet", {
    method: "DELETE",
  });
}

export function login(username: string, password: string) {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request<{ ok: boolean }>("/auth/logout", { method: "POST" });
}

export function getMe() {
  return request<CurrentUser>("/auth/me");
}

export function listAdminUsers() {
  return request<User[]>("/admin/users");
}

export function createAdminUser(payload: {
  email: string;
  username: string;
  password: string;
  role: "super_user" | "admin" | "trader" | "viewer";
  is_active?: boolean;
}) {
  return request<User>("/admin/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminUser(userId: number, payload: Partial<Pick<User, "email" | "username" | "role" | "is_active">>) {
  return request<User>(`/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function resetAdminUserPassword(userId: number, newPassword: string) {
  return request<{ ok: boolean }>(`/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ new_password: newPassword }),
  });
}

export function getTradingReadiness() {
  return request<TradingReadiness>("/trading/readiness");
}

export function getTradingStatus() {
  return request<TradingStatus>("/trading/status");
}

export function enableTrading() {
  return request<TradingStatus>("/trading/enable", {
    method: "POST",
    body: JSON.stringify({ confirm_phrase: REAL_TRADING_CONFIRMATION_PHRASE }),
  });
}

export function disableTrading() {
  return request<TradingStatus>("/trading/disable", { method: "POST" });
}

export function getApiBaseUrl() {
  return apiBaseUrl;
}
