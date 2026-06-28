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

      {!decision ? (
        <p className="mt-4 text-sm text-zinc-600">
          No strategy decision has been recorded yet. The strategy will evaluate when market and orderbook data are
          available.
        </p>
      ) : null}

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Outcome" value={decision?.outcome ?? "-"} />
        <Metric label="Strategy" value={readString(decision?.raw_context, "strategy_name") ?? "FINAL_3M_HIGHER_MARKET_PRICE"} />
        <Metric label="Market Price" value={formatNumber(decision?.market_price)} />
        <Metric label="Reason" value={decision?.reason ?? "-"} />
        <Metric label="UP Ask" value={formatNumber(decision?.up_ask)} />
        <Metric label="DOWN Ask" value={formatNumber(decision?.down_ask)} />
        <Metric label="Selected Side" value={readString(decision?.raw_context, "selected_side") ?? decision?.outcome ?? "-"} />
        <Metric label="Price Gap" value={formatNumber(readString(decision?.raw_context, "price_gap"))} />
        <Metric label="Time Remaining" value={formatSeconds(decision?.time_remaining_seconds)} />
        <Metric label="Risk Reasons" value={decision?.risk_reasons?.join(", ") || "-"} />
        <Metric label="Paper Order Status" value="-" />
      </div>
      {decision?.reason ? <p className="mt-3 text-sm text-zinc-600">{reasonMessage(decision.reason)}</p> : null}
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

function formatSeconds(value?: number | null) {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${value}s`;
}

function reasonMessage(reason?: string | null) {
  switch (reason) {
    case "ORDERBOOK_DATA_MISSING":
      return "The strategy cannot evaluate because UP or DOWN orderbook data is not available yet. Start the market data worker and wait for a fresh orderbook snapshot.";
    case "NOT_IN_FINAL_WINDOW":
      return "The strategy is waiting for the final 3-minute window.";
    case "PRICE_GAP_TOO_SMALL":
      return "The difference between UP and DOWN prices is below the configured Min Price Gap.";
    case "MARKET_DATA_STALE":
      return "The latest UP/DOWN orderbook data is stale. Wait for a fresh snapshot from the market data worker.";
    case "SPREAD_TOO_HIGH":
      return "The selected side spread is above the configured Max Spread.";
    case "PAPER_TRADING_DISABLED":
      return "Paper trading is disabled, so no paper order will be created.";
    case "KILL_SWITCH_ACTIVE":
      return "Kill Switch is enabled, so no paper or real order will be created.";
    default:
      return reason ? reason.replaceAll("_", " ") : "-";
  }
}

function readString(value: Record<string, unknown> | null | undefined, key: string) {
  const next = value?.[key];
  if (typeof next === "string") {
    return next;
  }
  if (typeof next === "number") {
    return String(next);
  }
  return null;
}
