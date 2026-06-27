type MetricCardProps = {
  label: string;
  value: string;
  detail?: string;
  tone?: "good" | "bad" | "neutral" | "warning";
};

export function MetricCard({ label, value, detail, tone = "neutral" }: MetricCardProps) {
  const valueClass =
    tone === "good"
      ? "text-accent"
      : tone === "bad"
        ? "text-danger"
        : tone === "warning"
          ? "text-amber-700"
          : "text-ink";

  return (
    <div className="min-w-0 rounded-md border border-zinc-200 bg-white p-4">
      <p className="text-xs font-medium uppercase text-muted">{label}</p>
      <p className={`mt-2 truncate text-2xl font-bold ${valueClass}`}>{value}</p>
      {detail ? <p className="mt-2 truncate text-sm text-muted">{detail}</p> : null}
    </div>
  );
}

