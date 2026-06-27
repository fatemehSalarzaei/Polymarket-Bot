"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { getOrders } from "@/lib/api-client";
import type { Order } from "@/types/order";
import { OrdersTable } from "@/components/orders/orders-table";

export function OrdersClient() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      try {
        const data = await getOrders();
        if (!cancelled) {
          setOrders(data);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error(err instanceof Error ? err.message : "Failed to load orders");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="mx-auto max-w-7xl px-5 py-8">
      <div className="mb-6">
        <p className="text-sm font-semibold text-accent">Paper and guarded real order history</p>
        <h2 className="mt-1 text-3xl font-bold tracking-normal">Orders</h2>
      </div>
      {loading ? <div className="mb-4 rounded-md border border-zinc-200 bg-white p-4 text-sm text-muted">Loading</div> : null}
      <OrdersTable orders={orders} />
    </section>
  );
}

