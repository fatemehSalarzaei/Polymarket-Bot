import type { OrderbookSnapshot } from "@/types/market";
import { FreshnessBadge } from "@/components/ui/freshness-badge";

type OrderbookTableProps = {
  title: string;
  snapshot?: OrderbookSnapshot | null;
};

export function OrderbookTable({ title, snapshot }: OrderbookTableProps) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold">{title}</h3>
          <p className="mt-1 truncate text-sm text-muted">{snapshot?.token_id ?? "No token"}</p>
        </div>
        <FreshnessBadge timestamp={snapshot?.received_at} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Stat label="Best Bid" value={formatNumber(snapshot?.best_bid)} />
        <Stat label="Best Ask" value={formatNumber(snapshot?.best_ask)} />
        <Stat label="Spread" value={formatNumber(snapshot?.spread)} />
        <Stat label="Last Trade" value={formatNumber(snapshot?.last_trade_price)} />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <Levels title="Bids" levels={snapshot?.bids ?? []} />
        <Levels title="Asks" levels={snapshot?.asks ?? []} />
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <p className="mt-1 text-base font-semibold text-ink">{value}</p>
    </div>
  );
}

function Levels({ title, levels }: { title: string; levels: { price: string; size: string }[] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase text-muted">{title}</p>
      <div className="overflow-hidden rounded-md border border-zinc-200">
        <table className="w-full table-fixed text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Price</th>
              <th className="px-3 py-2">Size</th>
            </tr>
          </thead>
          <tbody>
            {levels.length ? (
              levels.slice(0, 8).map((level, index) => (
                <tr key={`${level.price}-${level.size}-${index}`} className="border-t border-zinc-100">
                  <td className="px-3 py-2 font-medium">{formatNumber(level.price)}</td>
                  <td className="px-3 py-2 text-muted">{formatNumber(level.size)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-4 text-muted" colSpan={2}>
                  No levels
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatNumber(value?: string | null) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return parsed.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

