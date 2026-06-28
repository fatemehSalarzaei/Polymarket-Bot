import type { CurrentMarketOrderbook, HealthResponse, Market } from "@/types/market";
import type { Order } from "@/types/order";
import type { AuditLog } from "@/types/log";
import type { PnlSummary } from "@/types/pnl";
import type { RedeemAttemptResult, RedeemRecord, RedeemStatusResponse } from "@/types/redeem";
import type { StrategyDecision, StrategySettings, StrategySettingsPatch } from "@/types/strategy";
import { ApiError, type StructuredError } from "@/types/error";

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

export function getApiBaseUrl() {
  return apiBaseUrl;
}
