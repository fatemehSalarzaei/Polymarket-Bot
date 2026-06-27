import type { Order } from "@/types/order";

type OrdersTableProps = {
  orders: Order[];
};

export function OrdersTable({ orders }: OrdersTableProps) {
  return (
    <div className="rounded-md border border-zinc-200 bg-white p-5">
      <h3 className="text-lg font-semibold">Orders</h3>
      <div className="mt-4 overflow-auto rounded-md border border-zinc-200">
        <table className="w-full min-w-[980px] table-fixed text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase text-muted">
            <tr>
              <th className="px-3 py-2">Market</th>
              <th className="px-3 py-2">Outcome</th>
              <th className="px-3 py-2">Mode</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2">Price</th>
              <th className="px-3 py-2">Size</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Fill</th>
              <th className="px-3 py-2">Reason</th>
              <th className="px-3 py-2">Submitted</th>
            </tr>
          </thead>
          <tbody>
            {orders.length ? (
              orders.map((order) => (
                <tr key={order.id} className="border-t border-zinc-100">
                  <td className="px-3 py-2">{order.market_id}</td>
                  <td className="px-3 py-2 font-semibold">{order.outcome}</td>
                  <td className="px-3 py-2">{order.mode}</td>
                  <td className="px-3 py-2">{order.side}</td>
                  <td className="px-3 py-2">{formatNumber(order.price)}</td>
                  <td className="px-3 py-2">{formatNumber(order.size)}</td>
                  <td className="px-3 py-2">{order.status}</td>
                  <td className="px-3 py-2">{fillPercent(order)}</td>
                  <td className="px-3 py-2 text-muted">{order.error_message ?? paperReason(order)}</td>
                  <td className="px-3 py-2">{formatDate(order.submitted_at)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-3 py-5 text-muted" colSpan={10}>
                  No orders recorded
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function fillPercent(order: Order) {
  const size = Number(order.size);
  const matched = Number(order.size_matched);
  if (!size || Number.isNaN(size) || Number.isNaN(matched)) {
    return "-";
  }
  return `${Math.round((matched / size) * 100)}%`;
}

function paperReason(order: Order) {
  return order.raw_response?.simulated ? "simulated fill" : "-";
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatNumber(value: string) {
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

