"use client";

import type { RedeemRecord, RedeemStatus } from "@/types/redeem";

const statusTones: Record<RedeemStatus, string> = {
  NOT_ELIGIBLE: "border-zinc-200 bg-zinc-50 text-zinc-700",
  READY_TO_REDEEM: "border-amber-200 bg-amber-50 text-amber-700",
  SKIPPED_DRY_RUN: "border-sky-200 bg-sky-50 text-sky-700",
  REDEEM_SUBMITTED: "border-indigo-200 bg-indigo-50 text-indigo-700",
  REDEEM_CONFIRMED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  REDEEM_FAILED: "border-red-200 bg-red-50 text-red-700",
  SKIPPED_PAPER_ONLY: "border-zinc-200 bg-zinc-50 text-zinc-700",
};

export function RedeemPanel({ redeems }: { redeems: RedeemRecord[] }) {
  return (
    <section className="mt-6 rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-ink">Redeem / Wallet</h3>
          <p className="text-sm text-muted">Resolved real winning positions return to pUSD only after redeem.</p>
        </div>
      </div>

      {redeems.length === 0 ? (
        <p className="mt-4 rounded-md bg-zinc-50 p-3 text-sm text-muted">No redeem records yet.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase text-muted">
              <tr>
                <th className="py-2 pr-4 font-semibold">Market</th>
                <th className="py-2 pr-4 font-semibold">Winner</th>
                <th className="py-2 pr-4 font-semibold">Status</th>
                <th className="py-2 pr-4 font-semibold">Tx</th>
                <th className="py-2 pr-4 font-semibold">Amount</th>
                <th className="py-2 pr-4 font-semibold">Balance</th>
                <th className="py-2 pr-4 font-semibold">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {redeems.map((redeem) => (
                <tr key={redeem.id}>
                  <td className="max-w-[12rem] truncate py-3 pr-4 text-zinc-700">{redeem.market_id}</td>
                  <td className="py-3 pr-4 font-medium text-ink">{redeem.winning_outcome}</td>
                  <td className="py-3 pr-4">
                    <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${statusTones[redeem.status]}`}>
                      {redeem.status}
                    </span>
                  </td>
                  <td className="max-w-[12rem] truncate py-3 pr-4 text-zinc-600">{redeem.tx_hash ?? "-"}</td>
                  <td className="py-3 pr-4 text-zinc-700">{formatDecimal(redeem.amount_redeemed)}</td>
                  <td className="py-3 pr-4 text-zinc-700">
                    {formatDecimal(redeem.balance_before)} / {formatDecimal(redeem.balance_after)}
                  </td>
                  <td className="max-w-[18rem] truncate py-3 pr-4 text-zinc-600">{redeem.error_message ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function RedeemStatusBadge({ status }: { status: RedeemStatus }) {
  return <span className={`rounded-md border px-2 py-1 text-xs font-semibold ${statusTones[status]}`}>{status}</span>;
}

function formatDecimal(value: string | null) {
  if (!value) {
    return "-";
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed.toFixed(4);
}
