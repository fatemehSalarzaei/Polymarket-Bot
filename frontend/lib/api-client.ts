import type { CurrentMarketOrderbook, HealthResponse, Market } from "@/types/market";
import type { Order } from "@/types/order";
import type { AuditLog } from "@/types/log";
import type { PnlSummary } from "@/types/pnl";
import type { RedeemAttemptResult, RedeemRecord, RedeemStatusResponse } from "@/types/redeem";
import type { StrategyDecision, StrategySettings, StrategySettingsPatch } from "@/types/strategy";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      ...init?.headers,
    },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
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

export function getApiBaseUrl() {
  return apiBaseUrl;
}
