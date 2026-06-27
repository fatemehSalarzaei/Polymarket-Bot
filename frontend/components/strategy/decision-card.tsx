import type { StrategyDecision } from "@/types/strategy";

type DecisionCardProps = {
  decision: StrategyDecision | null;
};

export function DecisionCard({ decision }: DecisionCardProps) {
  const tone =
    decision?.decision === "BUY_UP" || decision?.decision === "BUY_DOWN"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : "border-amber-200 bg-amber-50 text-amber-800";

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase text-muted">Current Decision</p>
          <h3 className="mt-1 text-2xl font-bold text-ink">{decision?.decision ?? "NO_DATA"}</h3>
        </div>
        <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-semibold ${tone}`}>
          {decision?.risk_passed ? "Risk passed" : "No trade"}
        </span>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Outcome" value={decision?.outcome ?? "-"} />
        <Metric label="Edge" value={formatNumber(decision?.edge)} />
        <Metric label="Market Price" value={formatNumber(decision?.market_price)} />
        <Metric label="Reason" value={decision?.reason ?? "-"} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}

function formatNumber(value?: string | null) {
  if (!value) {
    return "-";
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

