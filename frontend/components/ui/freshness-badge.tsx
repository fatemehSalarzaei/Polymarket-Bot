"use client";

type FreshnessBadgeProps = {
  timestamp?: string | null;
  maxAgeSeconds?: number;
};

export function FreshnessBadge({ timestamp, maxAgeSeconds = 10 }: FreshnessBadgeProps) {
  const ageSeconds = getAgeSeconds(timestamp);
  const fresh = ageSeconds !== null && ageSeconds <= maxAgeSeconds;

  const label =
    ageSeconds === null
      ? "No data"
      : fresh
        ? `${Math.max(0, Math.round(ageSeconds))}s`
        : `Stale ${Math.round(ageSeconds)}s`;

  return (
    <span
      className={`inline-flex min-h-6 items-center rounded-md border px-2 text-xs font-semibold ${
        fresh ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800"
      }`}
    >
      {label}
    </span>
  );
}

function getAgeSeconds(timestamp?: string | null) {
  if (!timestamp) {
    return null;
  }
  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) {
    return null;
  }
  return (Date.now() - value) / 1000;
}

