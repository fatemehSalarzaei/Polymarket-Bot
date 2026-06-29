"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  configureWallet,
  deleteWalletCredentials,
  deriveWalletApiCredentials,
  getWalletStatus,
  testWalletCredentials,
} from "@/lib/api-client";
import { ApiError, type StructuredError } from "@/types/error";
import type { WalletStatus, WalletTestResponse } from "@/types/wallet";

const signatureTypes = [
  { value: 0, label: "0: EOA / private-key wallet" },
  { value: 1, label: "1: Proxy wallet" },
  { value: 2, label: "2: Gnosis Safe" },
  { value: 3, label: "3: Deposit / POLY_1271 wallet" },
];

export function WalletSettingsClient() {
  const [status, setStatus] = useState<WalletStatus | null>(null);
  const [testResult, setTestResult] = useState<WalletTestResponse | null>(null);
  const [privateKey, setPrivateKey] = useState("");
  const [funderAddress, setFunderAddress] = useState("");
  const [signatureType, setSignatureType] = useState(0);
  const [chainId, setChainId] = useState(137);
  const [deriveCredentials, setDeriveCredentials] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [showPrivateKey, setShowPrivateKey] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<StructuredError | string | null>(null);

  async function loadStatus() {
    try {
      setStatus(await getWalletStatus());
    } catch (err) {
      setError(errorPayload(err));
    }
  }

  useEffect(() => {
    void loadStatus();
  }, []);

  async function runAction<T>(action: () => Promise<T>, onSuccess: (result: T) => void, successMessage: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await action();
      onSuccess(result);
      toast.success(successMessage);
    } catch (err) {
      const payload = errorPayload(err);
      setError(payload);
      toast.error(readableError(payload));
    } finally {
      setLoading(false);
    }
  }

  function submitConfigure() {
    if (signatureType === 3 && !funderAddress.trim()) {
      setError("Funder / deposit wallet address is required for signature type 3.");
      return;
    }
    void runAction(
      () =>
        configureWallet({
          private_key: privateKey,
          funder_address: signatureType === 0 ? null : funderAddress || null,
          signature_type: signatureType,
          chain_id: chainId,
          derive_api_credentials: deriveCredentials,
        }),
      (nextStatus) => {
        setStatus(nextStatus);
        setPrivateKey("");
        setTestResult(null);
      },
      "Wallet configuration saved",
    );
  }

  return (
    <section className="mx-auto max-w-6xl px-5 py-8">
      <div className="mb-6">
        <p className="text-sm font-semibold text-accent">Wallet</p>
        <h2 className="text-3xl font-bold tracking-tight">Polymarket Credentials</h2>
      </div>

      {error ? <ErrorPanel error={error} /> : null}

      <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
        <section className="rounded-md border border-zinc-200 bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold">Status</h3>
            <StatusBadge configured={Boolean(status?.configured)} />
          </div>
          <div className="mt-4 grid gap-3 text-sm">
            <Info label="Wallet configured" value={status?.configured ? "yes" : "no"} />
            <Info label="Derived wallet address" value={maskAddress(status?.wallet_address)} />
            <Info label="API credentials configured" value={status?.api_key_configured ? "yes" : "no"} />
            <Info label="Trading ready" value={status?.configured && status.api_key_configured && status.chain_id === 137 && (status.signature_type !== 3 || Boolean(status.funder_address)) ? "yes" : "no"} />
            <Info label="API Key" value={status?.api_key_configured ? status.api_key_masked ?? "configured" : "not configured"} />
            <Info label="Signature Type" value={status?.signature_type?.toString() ?? "-"} />
            <Info label="Chain ID" value={status?.chain_id?.toString() ?? "-"} />
            <Info label="Funder Address" value={maskAddress(status?.funder_address)} />
            <Info label="Last Validated" value={formatDate(status?.last_validated_at)} />
            <Info label="Last Error" value={status?.last_error ?? "-"} />
            <Info label="Updated" value={formatDate(status?.updated_at)} />
          </div>

          {testResult ? (
            <div className="mt-4 rounded-md border border-zinc-200 bg-zinc-50 p-3 text-sm">
              <p className="font-semibold">{testResult.message}</p>
              <p className="mt-1 text-zinc-600">Trading ready: {testResult.trading_ready ? "yes" : "no"}</p>
              {testResult.issues.length ? <p className="mt-1 text-red-700">{testResult.issues.join(", ")}</p> : null}
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap gap-2">
            <button className="btn-secondary" disabled={loading} onClick={() => void runAction(testWalletCredentials, setTestResult, "Credential test complete")}>
              Test Credentials
            </button>
            <button className="btn-secondary" disabled={loading || !status?.configured} onClick={() => void runAction(deriveWalletApiCredentials, setStatus, "API credentials re-derived")}>
              Re-derive API Credentials
            </button>
            <button className="btn-danger" disabled={loading || !status?.configured} onClick={() => void runAction(deleteWalletCredentials, setStatus, "Wallet configuration deleted")}>
              Delete
            </button>
          </div>
        </section>

        <section className="rounded-md border border-zinc-200 bg-white p-5">
          <h3 className="font-semibold">Configure Wallet</h3>
          <p className="mt-2 text-sm text-zinc-600">
            Simple setup only needs your private key. The backend derives your wallet address and Polymarket API credentials.
          </p>
          <div className="mt-4 grid gap-4">
            <label className="grid gap-1 text-sm font-medium">
              Private Key
              <div className="flex rounded-md border border-zinc-300 bg-white focus-within:border-zinc-500">
                <input
                  className="min-w-0 flex-1 rounded-l-md px-3 py-2 font-mono text-sm outline-none"
                  type={showPrivateKey ? "text" : "password"}
                  value={privateKey}
                  onChange={(event) => setPrivateKey(event.target.value)}
                  placeholder="0x..."
                />
                <button className="px-3 text-zinc-600" type="button" onClick={() => setShowPrivateKey((value) => !value)} aria-label="Toggle private key visibility">
                  {showPrivateKey ? "Hide" : "Show"}
                </button>
              </div>
            </label>
            <div className="rounded-md border border-zinc-200 bg-zinc-50">
              <button
                className="flex w-full items-center justify-between px-3 py-3 text-left"
                type="button"
                onClick={() => setAdvancedOpen((value) => !value)}
              >
                <span>
                  <span className="block text-sm font-semibold text-ink">Advanced wallet settings</span>
                  <span className="mt-1 block text-xs text-zinc-600">
                    Only use these settings if your Polymarket account uses a deposit/proxy/smart-contract wallet.
                  </span>
                </span>
                <span className="text-sm font-semibold text-accent">{advancedOpen ? "Hide" : "Show"}</span>
              </button>
              {advancedOpen ? (
                <div className="grid gap-4 border-t border-zinc-200 p-3">
                  <label className="grid gap-1 text-sm font-medium">
                    Signature Type
                    <select className="input" value={signatureType} onChange={(event) => setSignatureType(Number(event.target.value))}>
                      {signatureTypes.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {signatureType !== 0 ? (
                    <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
                      Proxy, Safe, and deposit wallet modes may require a funder/deposit wallet address.
                    </p>
                  ) : null}
                  {signatureType !== 0 ? (
                    <label className="grid gap-1 text-sm font-medium">
                      Funder / Deposit Wallet Address
                      <input className="input" value={funderAddress} onChange={(event) => setFunderAddress(event.target.value)} placeholder="0x..." required={signatureType === 3} />
                    </label>
                  ) : null}
                  <label className="grid gap-1 text-sm font-medium">
                    Chain ID
                    <input className="input" type="number" value={chainId} onChange={(event) => setChainId(Number(event.target.value))} />
                  </label>
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input type="checkbox" checked={deriveCredentials} onChange={(event) => setDeriveCredentials(event.target.checked)} />
                    Derive API credentials
                  </label>
                </div>
              ) : null}
            </div>
            <button className="btn-primary w-fit" disabled={loading || !privateKey || (signatureType === 3 && !funderAddress.trim())} onClick={submitConfigure}>
              Save Wallet
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}

function StatusBadge({ configured }: { configured: boolean }) {
  return (
    <span className={`rounded-md px-2 py-1 text-xs font-semibold ${configured ? "bg-emerald-100 text-emerald-800" : "bg-zinc-100 text-zinc-700"}`}>
      {configured ? "configured" : "not configured"}
    </span>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-md bg-zinc-50 p-3">
      <span className="text-xs uppercase text-zinc-500">{label}</span>
      <span className="break-all font-medium text-zinc-900">{value}</span>
    </div>
  );
}

function ErrorPanel({ error }: { error: StructuredError | string }) {
  if (typeof error === "string") {
    return <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>;
  }
  return (
    <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <p className="font-semibold">{error.title}</p>
      <p className="mt-1">{error.message}</p>
      {error.recovery_actions.length ? (
        <ul className="mt-3 list-disc space-y-1 pl-5">
          {error.recovery_actions.map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
      ) : null}
      {process.env.NODE_ENV === "development" && error.technical_detail ? (
        <pre className="mt-3 overflow-auto rounded-md bg-white/70 p-2 text-xs text-red-950">{error.technical_detail}</pre>
      ) : null}
    </div>
  );
}

function errorPayload(err: unknown): StructuredError | string {
  if (err instanceof ApiError && err.structured) {
    return err.structured;
  }
  if (err instanceof ApiError) {
    return err.message;
  }
  return err instanceof Error ? err.message : "Request failed";
}

function readableError(error: StructuredError | string) {
  return typeof error === "string" ? error : `${error.title}: ${error.message}`;
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

function maskAddress(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value;
}
