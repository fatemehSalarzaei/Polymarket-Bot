import type { PnlSummary } from "@/types/pnl";
import { MetricCard } from "@/components/dashboard/metric-card";

export function PnlCards({ summary }: { summary: PnlSummary | null }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard label="Paper PnL" value={formatCurrency(summary?.paper_pnl)} />
      <MetricCard label="Real PnL" value={formatCurrency(summary?.real_pnl)} />
      <MetricCard label="Settled Markets" value={String(summary?.settled_markets ?? 0)} />
      <MetricCard label="Win Rate" value={formatPercent(summary?.win_rate)} />
      <MetricCard label="Paper Orders" value={String(summary?.paper_orders ?? 0)} />
      <MetricCard label="Real Orders" value={String(summary?.real_orders ?? 0)} />
      <MetricCard label="No Trade Count" value={String(summary?.no_trade_count ?? 0)} />
      <MetricCard label="Resolved Record" value={`${summary?.winning_trades ?? 0}/${summary?.losing_trades ?? 0}`} />
    </div>
  );
}

function formatCurrency(value?: string) {
  const parsed = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number.isNaN(parsed) ? 0 : parsed);
}

function formatPercent(value?: string) {
  const parsed = Number(value ?? 0);
  return `${((Number.isNaN(parsed) ? 0 : parsed) * 100).toFixed(1)}%`;
}

