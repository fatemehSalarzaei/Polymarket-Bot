import type { StrategyDecision } from "@/types/strategy";

type DecisionHistoryProps = {
  decisions: StrategyDecision[];
};

export function DecisionHistory({ decisions }: DecisionHistoryProps) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-5">
      <h3 className="text-lg font-semibold">Decision History</h3>
      <div className="mt-4 overflow-hidden rounded-md border border-zinc-200">
        <table className="w-full min-w-[760px] table-fixed text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Decision</th>
              <th className="px-3 py-2">Outcome</th>
              <th className="px-3 py-2">Edge</th>
              <th className="px-3 py-2">Spread</th>
              <th className="px-3 py-2">Reason</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length ? (
              decisions.map((decision) => (
                <tr key={decision.id} className="border-t border-zinc-100">
                  <td className="px-3 py-2">{formatDate(decision.created_at)}</td>
                  <td className="px-3 py-2 font-semibold">{decision.decision}</td>
                  <td className="px-3 py-2">{decision.outcome ?? "-"}</td>
                  <td className="px-3 py-2">{formatNumber(decision.edge)}</td>
                  <td className="px-3 py-2">{formatNumber(decision.spread)}</td>
                  <td className="px-3 py-2 text-muted">{decision.reason ?? "-"}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-5 text-muted" colSpan={6}>
                  No decisions recorded
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatNumber(value?: string | null) {
  if (!value) {
    return "-";
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

